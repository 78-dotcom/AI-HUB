from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from typing import Any

import httpx
from accounts import Base, _db, account_user
from conversations import persist_voice_turn
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Index, Integer, String, and_, case, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
import websockets

router = APIRouter(prefix="/api/voice", tags=["voice"])

SUPPORTED_LANGUAGES = {"en", "ru", "es", "fr", "de"}
SUPPORTED_REALTIME_MODELS = {
    "gpt-realtime-2.1-mini",
    "gpt-realtime-2.1",
    "gpt-realtime-2",
    "gpt-realtime-1.5",
}
CLIENT_SECRET_TTL_SECONDS = 60
VOICE_SESSION_WINDOW_SECONDS = 60 * 60
VOICE_SESSION_MAX_PER_WINDOW = 12
VOICE_SESSION_MIN_INTERVAL_SECONDS = 5
OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"


class VoiceSessionQuota(Base):
    __tablename__ = "voice_session_quotas"

    identity_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_issued_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class VoiceSessionBody(BaseModel):
    language: str = Field(default="en", pattern="^(en|ru|es|fr|de)$")


class VoiceTranscriptBody(BaseModel):
    conversation_id: str | None = Field(default=None, max_length=36)
    model: str = Field(min_length=1, max_length=100)
    user_text: str = Field(min_length=1, max_length=12000)
    assistant_text: str = Field(min_length=1, max_length=12000)



def _voice_identity(request: Request) -> str:
    user = account_user(request)
    if user and user.get("id"):
        raw_identity = f"account:{user['id']}"
    else:
        # Workspace-only sessions have no account ID. Hash the signed session
        # cookie rather than retaining a credential or raw client address.
        raw_identity = f"workspace:{request.cookies.get('aihub_session', '')}"
    return hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()


def _check_voice_session_rate_limit(request: Request, now: float | None = None) -> None:
    """Atomically enforce persistent per-identity issuance limits in the shared SQL database."""
    current = int(time.time() if now is None else now)
    identity = _voice_identity(request)
    with _db() as db:
        dialect = db.bind.dialect.name
        values = {
            "identity_hash": identity,
            "window_started_at": current,
            "issued_count": 0,
            "last_issued_at": 0,
        }
        if dialect == "postgresql":
            insert_stmt = postgres_insert(VoiceSessionQuota).values(**values).on_conflict_do_nothing(
                index_elements=["identity_hash"]
            )
        elif dialect == "sqlite":
            insert_stmt = sqlite_insert(VoiceSessionQuota).values(**values).on_conflict_do_nothing(
                index_elements=["identity_hash"]
            )
        else:
            raise HTTPException(
                status_code=503,
                detail="Persistent voice session limits are not supported by the configured database.",
            )
        db.execute(insert_stmt)

        expired_window = VoiceSessionQuota.window_started_at <= current - VOICE_SESSION_WINDOW_SECONDS
        cooldown_elapsed = or_(
            VoiceSessionQuota.last_issued_at == 0,
            VoiceSessionQuota.last_issued_at <= current - VOICE_SESSION_MIN_INTERVAL_SECONDS,
        )
        can_issue = or_(
            expired_window,
            and_(
                VoiceSessionQuota.issued_count < VOICE_SESSION_MAX_PER_WINDOW,
                cooldown_elapsed,
            ),
        )
        result = db.execute(
            update(VoiceSessionQuota)
            .where(VoiceSessionQuota.identity_hash == identity, can_issue)
            .values(
                window_started_at=case(
                    (expired_window, current),
                    else_=VoiceSessionQuota.window_started_at,
                ),
                issued_count=case(
                    (expired_window, 1),
                    else_=VoiceSessionQuota.issued_count + 1,
                ),
                last_issued_at=current,
            )
        )
        if result.rowcount == 1:
            return

        row = db.execute(
            select(VoiceSessionQuota).where(VoiceSessionQuota.identity_hash == identity)
        ).scalar_one()
        if row.last_issued_at and current - row.last_issued_at < VOICE_SESSION_MIN_INTERVAL_SECONDS:
            retry_after = max(1, VOICE_SESSION_MIN_INTERVAL_SECONDS - (current - row.last_issued_at))
            raise HTTPException(
                status_code=429,
                detail="Please wait a few seconds before starting another voice session.",
                headers={"Retry-After": str(retry_after)},
            )
        retry_after = max(1, VOICE_SESSION_WINDOW_SECONDS - (current - row.window_started_at))
        raise HTTPException(
            status_code=429,
            detail="Voice session limit reached for this account. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _voice_auth(request: Request) -> None:
    auth = getattr(request.app.state, "voice_auth", None)
    if not callable(auth):
        raise HTTPException(status_code=503, detail="Voice authentication is not configured.")
    auth(request)


def _realtime_model() -> str:
    requested = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1-mini").strip()
    if requested not in SUPPORTED_REALTIME_MODELS:
        raise HTTPException(status_code=503, detail="The configured realtime voice model is not supported.")
    return requested


def _extract_client_secret(payload: Any) -> tuple[str, int | None]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid realtime provider response.")
    secret = payload.get("client_secret")
    if isinstance(secret, dict):
        value = secret.get("value")
        expires_at = secret.get("expires_at")
    else:
        value = payload.get("value")
        expires_at = payload.get("expires_at")
    if not isinstance(value, str) or not value.startswith("ek_"):
        raise ValueError("Realtime provider did not return a client secret.")
    if not isinstance(expires_at, int):
        expires_at = None
    return value, expires_at


@router.get("/capabilities")
async def voice_capabilities(request: Request) -> dict[str, Any]:
    _voice_auth(request)
    configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
    model = _realtime_model() if configured else None
    return {
        "dictation": True,
        "realtime_voice": configured,
        "provider": "openai" if configured else None,
        "model": model,
        "requires_microphone_permission": True,
        "raw_audio_stored_by_ai_hub": False,
    }


@router.post("/session")
async def create_voice_session(body: VoiceSessionBody, request: Request) -> dict[str, Any]:
    """Mint a short-lived, scoped Realtime client secret; never expose the project API key."""
    _voice_auth(request)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Realtime voice is not configured yet.")

    _check_voice_session_rate_limit(request)
    model = _realtime_model()
    language_names = {
        "en": "English", "ru": "Russian", "es": "Spanish",
        "fr": "French", "de": "German",
    }
    session_config = {
        "type": "realtime",
        "model": model,
        "instructions": (
            "You are the voice assistant inside AI HUB. "
            f"Speak naturally and answer in {language_names[body.language]} unless the user asks otherwise. "
            "Be helpful, clear, and concise. Let the user interrupt you at any time."
        ),
        "audio": {
            "input": {
                "noise_reduction": {"type": "near_field"},
                "transcription": {"model": "gpt-live-transcribe", "language": body.language},
                "turn_detection": {
                    "type": "server_vad",
                    "create_response": True,
                    "interrupt_response": True,
                    "silence_duration_ms": 500,
                },
            },
            "output": {"voice": os.getenv("OPENAI_REALTIME_VOICE", "marin")},
        },
        "output_modalities": ["audio"],
        "max_output_tokens": 512,
    }
    payload = {
        "expires_after": {"anchor": "created_at", "seconds": CLIENT_SECRET_TTL_SECONDS},
        "session": session_config,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    user = account_user(request)
    if user and user.get("id"):
        # Stable, privacy-preserving identifier recommended for Realtime requests.
        headers["OpenAI-Safety-Identifier"] = hashlib.sha256(
            str(user["id"]).encode("utf-8")
        ).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            response = await client.post(
                OPENAI_CLIENT_SECRETS_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            provider_payload = response.json()
        client_secret, expires_at = _extract_client_secret(provider_payload)
    except httpx.HTTPStatusError as exc:
        # Do not relay provider response bodies: they may contain sensitive diagnostics.
        raise HTTPException(status_code=502, detail="The voice provider could not create a session.") from exc
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Could not start a realtime voice session.") from exc

    return {
        "provider": "openai",
        "model": model,
        "client_secret": client_secret,
        "expires_at": expires_at,
        "client_secret_ttl_seconds": CLIENT_SECRET_TTL_SECONDS,
        "transport": "webrtc",
        "raw_audio_stored_by_ai_hub": False,
    }



@router.post("/transcript")
async def save_voice_transcript(body: VoiceTranscriptBody, request: Request) -> dict[str, Any]:
    """Save text transcript only; never accept or store microphone audio."""
    _voice_auth(request)
    if body.model not in SUPPORTED_REALTIME_MODELS:
        raise HTTPException(status_code=400, detail="Unsupported realtime voice model.")
    conversation_id = persist_voice_turn(
        request, body.conversation_id, body.model, body.user_text, body.assistant_text
    )
    return {
        "conversation_id": conversation_id,
        "persisted": conversation_id is not None,
        "raw_audio_stored_by_ai_hub": False,
    }


VOICE_MAX_DURATION_SECONDS = 10 * 60
VOICE_SIDEBAND_URL = "wss://api.openai.com/v1/realtime?call_id={call_id}"
VOICE_CALL_ID_PATTERN = re.compile(r"^rtc_[A-Za-z0-9_-]{6,100}$")
VOICE_CLOSE_FINALIZATION_SECONDS = 8


class VoiceAttachBody(BaseModel):
    call_id: str = Field(min_length=10, max_length=110, pattern=r"^rtc_[A-Za-z0-9_-]{6,100}$")


class VoiceSessionControl(Base):
    __tablename__ = "voice_session_controls"

    call_id: Mapped[str] = mapped_column(String(110), primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ends_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="connecting")
    usage_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finalization_confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)


Index(
    "uq_voice_session_controls_active_identity",
    VoiceSessionControl.identity_hash,
    unique=True,
    postgresql_where=text("status IN ('connecting', 'active')"),
    sqlite_where=text("status IN ('connecting', 'active')"),
)


def _update_voice_control(
    call_id: str,
    *,
    status: str | None = None,
    usage_seconds: int | None = None,
    closed_at: int | None = None,
    finalization_confirmed: bool | None = None,
) -> None:
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
    if usage_seconds is not None:
        values["usage_seconds"] = max(0, int(usage_seconds))
    if closed_at is not None:
        values["closed_at"] = int(closed_at)
    if finalization_confirmed is not None:
        values["finalization_confirmed"] = bool(finalization_confirmed)
    if not values:
        return
    with _db() as db:
        db.execute(
            update(VoiceSessionControl)
            .where(VoiceSessionControl.call_id == call_id)
            .values(**values)
        )


def _event_usage_seconds(event: Any) -> int | None:
    if not isinstance(event, dict):
        return None
    usage = event.get("usage")
    if not isinstance(usage, dict):
        return None
    seconds = usage.get("seconds")
    if isinstance(seconds, (int, float)) and seconds >= 0:
        return int(seconds)
    return None


async def _run_voice_sideband(
    call_id: str,
    ends_at: int,
    ready: asyncio.Event,
    state: dict[str, Any],
) -> None:
    """Attach a server-owned control socket and close the provider session at its deadline."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    usage_seconds: int | None = None
    finalization_confirmed = False
    final_status = "incomplete"
    upstream = None
    try:
        url = VOICE_SIDEBAND_URL.format(call_id=call_id)
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {api_key}"},
            open_timeout=10,
            close_timeout=5,
            ping_interval=20,
            max_size=2**20,
        ) as connection:
            upstream = connection
            _update_voice_control(call_id, status="active")
            state["connected"] = True
            ready.set()

            close_requested = False
            close_deadline: float | None = None
            while True:
                now = time.time()
                if not close_requested and now >= ends_at:
                    await connection.send(json.dumps({"type": "session.close"}))
                    close_requested = True
                    close_deadline = now + VOICE_CLOSE_FINALIZATION_SECONDS

                if close_requested and close_deadline is not None and time.time() >= close_deadline:
                    break

                timeout = 1.0
                if not close_requested:
                    timeout = max(0.05, min(timeout, ends_at - time.time()))
                elif close_deadline is not None:
                    timeout = max(0.05, min(timeout, close_deadline - time.time()))

                try:
                    raw_event = await asyncio.wait_for(connection.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    continue

                try:
                    event = json.loads(raw_event)
                except (TypeError, ValueError):
                    continue
                latest_usage = _event_usage_seconds(event)
                if latest_usage is not None:
                    usage_seconds = latest_usage
                    _update_voice_control(call_id, usage_seconds=usage_seconds)
                if isinstance(event, dict) and event.get("type") == "session.closed":
                    final_usage = _event_usage_seconds(event)
                    if final_usage is not None:
                        usage_seconds = final_usage
                    finalization_confirmed = True
                    final_status = "ended"
                    break

            if close_requested and not finalization_confirmed:
                final_status = "incomplete"
            elif not close_requested:
                # The primary WebRTC session ended before our deadline.
                final_status = "ended"
    except asyncio.CancelledError:
        final_status = "incomplete"
        raise
    except Exception as exc:
        # Keep provider diagnostics and credentials out of client responses and logs.
        state["error"] = type(exc).__name__
        final_status = "failed" if not ready.is_set() else "incomplete"
    finally:
        if not ready.is_set():
            ready.set()
        try:
            _update_voice_control(
                call_id,
                status=final_status,
                usage_seconds=usage_seconds,
                closed_at=int(time.time()),
                finalization_confirmed=finalization_confirmed,
            )
        except Exception:
            # The session is still closed upstream where possible; database reconciliation
            # will show this record as incomplete if persistence is unavailable.
            pass


@router.post("/attach")
async def attach_voice_control(body: VoiceAttachBody, request: Request) -> dict[str, Any]:
    """Attach an authenticated server-side controller to the user's existing WebRTC call."""
    _voice_auth(request)
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="Realtime voice is not configured yet.")
    if not VOICE_CALL_ID_PATTERN.fullmatch(body.call_id):
        raise HTTPException(status_code=400, detail="Invalid voice call identifier.")

    identity_hash = _voice_identity(request)
    now = int(time.time())
    ends_at = now + VOICE_MAX_DURATION_SECONDS
    try:
        with _db() as db:
            db.add(
                VoiceSessionControl(
                    call_id=body.call_id,
                    identity_hash=identity_hash,
                    started_at=now,
                    ends_at=ends_at,
                    status="connecting",
                    finalization_confirmed=False,
                )
            )
            db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A voice session is already active, or this call was already registered.",
        ) from exc

    ready = asyncio.Event()
    state: dict[str, Any] = {}
    tasks = getattr(request.app.state, "voice_sideband_tasks", None)
    if tasks is None:
        tasks = {}
        request.app.state.voice_sideband_tasks = tasks
    task = asyncio.create_task(_run_voice_sideband(body.call_id, ends_at, ready, state))
    tasks[body.call_id] = task
    task.add_done_callback(lambda completed, key=body.call_id, registry=tasks: registry.pop(key, None))

    try:
        await asyncio.wait_for(ready.wait(), timeout=12)
    except asyncio.TimeoutError as exc:
        task.cancel()
        raise HTTPException(status_code=502, detail="Could not attach server-side voice controls.") from exc

    if state.get("error"):
        await task
        raise HTTPException(status_code=502, detail="Could not attach server-side voice controls.")

    return {
        "call_id": body.call_id,
        "server_controlled": True,
        "started_at": now,
        "ends_at": ends_at,
        "max_duration_seconds": VOICE_MAX_DURATION_SECONDS,
        "usage_tracking": "provider_reported",
    }
