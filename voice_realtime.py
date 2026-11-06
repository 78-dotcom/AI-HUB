from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx
from accounts import account_user
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/voice", tags=["voice"])

SUPPORTED_LANGUAGES = {"en", "ru", "es", "fr", "de"}
SUPPORTED_REALTIME_MODELS = {
    "gpt-realtime-2.1-mini",
    "gpt-realtime-2.1",
    "gpt-realtime-2",
    "gpt-realtime-1.5",
}
CLIENT_SECRET_TTL_SECONDS = 60
OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"


class VoiceSessionBody(BaseModel):
    language: str = Field(default="en", pattern="^(en|ru|es|fr|de)$")


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
