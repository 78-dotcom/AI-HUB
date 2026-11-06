from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from contextlib import suppress
from urllib.parse import quote, urlparse

import websockets
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from accounts import _db
from voice_realtime import (
    VOICE_MAX_DURATION_SECONDS,
    VOICE_SESSION_MAX_ESTIMATED_COST_USD,
    VoiceSessionControl,
    _check_voice_session_rate_limit,
    _update_voice_control,
    _voice_auth,
    _voice_identity,
)

router = APIRouter(prefix="/api/voice", tags=["voice"])

GEMINI_LIVE_DEFAULT_MODEL = "gemini-3.8-live"
GEMINI_FREE_TIER_MODEL = "gemini-3.8-live"
GEMINI_PAID_AUDIO_USD_PER_MINUTE = 0.023
MAX_CLIENT_MESSAGE_BYTES = 1024 * 1024


def gemini_model() -> str:
    return os.getenv("GEMINI_LIVE_MODEL", GEMINI_LIVE_DEFAULT_MODEL).strip() or GEMINI_LIVE_DEFAULT_MODEL


def gemini_is_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def gemini_session_cost(started_at: int, now: int | None = None) -> float:
    """Conservative elapsed-time estimate for a paid Gemini Live project.

    The free tier is zero-priced. Set GEMINI_BILLING_TIER=paid when the Google
    AI Studio project has billing enabled; the estimate assumes both input and
    output audio for every minute and is deliberately conservative.
    """
    tier = os.getenv("GEMINI_BILLING_TIER", "free").strip().lower()
    if tier == "free" and gemini_model() == GEMINI_FREE_TIER_MODEL:
        return 0.0
    current = int(time.time() if now is None else now)
    elapsed_minutes = max(0, min(current - started_at, VOICE_MAX_DURATION_SECONDS)) / 60
    return round(elapsed_minutes * GEMINI_PAID_AUDIO_USD_PER_MINUTE, 8)


def _gemini_url() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Gemini Live is not configured.")
    return (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        f"?key={quote(api_key, safe='')}"
    )


def _origin_is_same_site(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin", "")
    if not origin:
        return False
    parsed = urlparse(origin)
    expected_host = websocket.url.hostname
    secure = parsed.scheme == "https" or (
        parsed.scheme == "http" and expected_host in {"localhost", "127.0.0.1"}
    )
    return bool(secure and parsed.hostname and parsed.hostname.lower() == (expected_host or "").lower())


def _usage_counts(event: object) -> tuple[int, int] | None:
    if not isinstance(event, dict):
        return None
    usage = event.get("usageMetadata") or event.get("usage_metadata")
    if not isinstance(usage, dict):
        return None
    incoming = usage.get("promptTokenCount", usage.get("prompt_token_count", 0))
    outgoing = usage.get("candidatesTokenCount", usage.get("candidates_token_count", 0))
    try:
        return max(0, int(incoming or 0)), max(0, int(outgoing or 0))
    except (TypeError, ValueError):
        return None


@router.get("/providers")
async def voice_providers(request: Request) -> dict[str, object]:
    _voice_auth(request)
    providers = []
    if gemini_is_configured():
        providers.append({
            "id": "gemini",
            "name": "Gemini Live",
            "model": gemini_model(),
            "pricing": (
                "free" if os.getenv("GEMINI_BILLING_TIER", "free").strip().lower() == "free"
                and gemini_model() == GEMINI_FREE_TIER_MODEL else "paid_estimate"
            ),
            "free_tier_eligible": gemini_model() == GEMINI_FREE_TIER_MODEL,
        })
    if os.getenv("OPENAI_API_KEY", "").strip():
        from voice_realtime import _realtime_model
        providers.append({
            "id": "openai",
            "name": "OpenAI Realtime",
            "model": _realtime_model(),
            "pricing": "paid",
            "free_tier_eligible": False,
        })
    return {
        "providers": providers,
        "max_session_seconds": VOICE_MAX_DURATION_SECONDS,
        "max_estimated_cost_usd": VOICE_SESSION_MAX_ESTIMATED_COST_USD,
    }


@router.websocket("/gemini")
async def gemini_live_relay(websocket: WebSocket) -> None:
    try:
        _voice_auth(websocket)
    except HTTPException:
        await websocket.close(code=4401, reason="Sign in required")
        return
    if not _origin_is_same_site(websocket):
        await websocket.close(code=4403, reason="Untrusted origin")
        return
    if not gemini_is_configured():
        await websocket.close(code=4400, reason="Gemini Live is not configured")
        return

    try:
        _check_voice_session_rate_limit(websocket)
    except HTTPException as exc:
        await websocket.close(code=4429, reason=exc.detail[:120])
        return

    identity_hash = _voice_identity(websocket)
    call_id = "gem_" + secrets.token_hex(16)
    started_at = int(time.time())
    ends_at = started_at + VOICE_MAX_DURATION_SECONDS
    try:
        with _db() as db:
            db.execute(
                update(VoiceSessionControl)
                .where(
                    VoiceSessionControl.identity_hash == identity_hash,
                    VoiceSessionControl.status.in_(("connecting", "active")),
                    VoiceSessionControl.ends_at <= started_at,
                )
                .values(
                    status="incomplete",
                    closed_at=started_at,
                    close_reason="controller_lease_expired",
                    finalization_confirmed=False,
                )
            )
            db.add(VoiceSessionControl(
                call_id=call_id,
                identity_hash=identity_hash,
                model=gemini_model(),
                started_at=started_at,
                ends_at=ends_at,
                status="connecting",
                finalization_confirmed=False,
            ))
            db.flush()
    except IntegrityError:
        await websocket.close(code=4409, reason="A voice session is already active")
        return

    await websocket.accept()
    upstream = None
    final_status = "failed"
    finalization_confirmed = False
    input_tokens = output_tokens = 0
    language = websocket.query_params.get("language", "en").lower()
    language_names = {
        "en": "English", "ru": "Russian", "es": "Spanish",
        "fr": "French", "de": "German",
    }
    response_language = language_names.get(language, "the user's language")
    try:
        upstream = await websockets.connect(
            _gemini_url(),
            open_timeout=15,
            close_timeout=3,
            max_size=MAX_CLIENT_MESSAGE_BYTES,
            ping_interval=20,
            ping_timeout=20,
        )
        await upstream.send(json.dumps({
            "setup": {
                "model": f"models/{gemini_model()}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": os.getenv("GEMINI_LIVE_VOICE", "Aoede")
                            }
                        }
                    },
                },
                "systemInstruction": {
                    "parts": [{
                        "text": (
                            "You are the live voice assistant inside AI HUB. "
                            f"Speak naturally and clearly in {response_language}, unless the user asks otherwise. "
                            "Keep answers conversational and let the user interrupt you."
                        )
                    }]
                },
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
            }
        }))
        _update_voice_control(call_id, status="active")

        async def client_to_google() -> None:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                payload = message.get("text")
                if payload is None:
                    payload = message.get("bytes")
                if payload is None:
                    continue
                size = len(payload.encode("utf-8")) if isinstance(payload, str) else len(payload)
                if size > MAX_CLIENT_MESSAGE_BYTES:
                    raise ValueError("Voice message too large")
                if not isinstance(payload, str):
                    raise ValueError("Binary client frames are not supported")
                parsed = json.loads(payload)
                if not isinstance(parsed, dict) or "realtimeInput" not in parsed:
                    raise ValueError("Only realtime audio input is accepted")
                await upstream.send(payload)

        async def google_to_client() -> None:
            nonlocal input_tokens, output_tokens
            async for message in upstream:
                if isinstance(message, str):
                    try:
                        event = json.loads(message)
                    except ValueError:
                        event = None
                    if isinstance(event, dict) and "setupComplete" in event:
                        await websocket.send_json({
                            "aiHub": {"type": "session.started", "started_at": started_at, "ends_at": ends_at}
                        })
                    counts = _usage_counts(event)
                    if counts:
                        input_tokens, output_tokens = counts
                        _update_voice_control(
                            call_id,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        )
                    await websocket.send_text(message)
                else:
                    await websocket.send_bytes(message)

        tasks = {
            asyncio.create_task(client_to_google()),
            asyncio.create_task(google_to_client()),
        }
        remaining_seconds = max(0, ends_at - int(time.time()))
        done, pending = await asyncio.wait(
            tasks, timeout=remaining_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if pending:
            for task in pending:
                task.cancel()
            for task in pending:
                with suppress(asyncio.CancelledError, Exception):
                    await task
        if not done:
            final_status = "ended"
            finalization_confirmed = False
            with suppress(Exception):
                await websocket.send_json({
                    "aiHub": {"type": "session.closed", "reason": "duration_limit"}
                })
            with suppress(Exception):
                await websocket.close(code=4408, reason="10-minute voice limit reached")
        else:
            final_status = "ended"
            finalization_confirmed = False
            with suppress(Exception):
                await websocket.close(code=1000, reason="Gemini Live session ended")
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        final_status = "ended"
        finalization_confirmed = True
    except Exception:
        final_status = "failed" if upstream is None else "incomplete"
        with suppress(Exception):
            await websocket.close(code=1011, reason="Gemini Live connection failed")
    finally:
        if upstream is not None:
            with suppress(Exception):
                await upstream.close()
        estimated_cost = gemini_session_cost(started_at)
        with suppress(Exception):
            _update_voice_control(
                call_id,
                status=final_status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
                closed_at=int(time.time()),
                finalization_confirmed=finalization_confirmed,
                close_reason="duration_limit" if int(time.time()) >= ends_at else "client_or_provider_closed",
            )
