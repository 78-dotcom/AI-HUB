from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import suppress
from urllib.parse import quote

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from accounts import account_user

router = APIRouter(tags=["voice"])

VOICE_SESSION_SECONDS = 10 * 60
MAX_VOICE_MESSAGE_BYTES = 4 * 1024 * 1024
_active_sessions: set[str] = set()


def _session_identity(websocket: WebSocket) -> str:
    user = account_user(websocket)
    if user:
        return "account:" + user["id"]
    # The legacy private-workspace cookie is signed by the main application.
    from web_app import _valid_session

    if _valid_session(websocket):
        token = websocket.cookies.get("aihub_session", "")
        return "workspace:" + hashlib.sha256(token.encode()).hexdigest()
    return ""


def available_voice_providers() -> list[dict[str, str]]:
    providers: list[dict[str, str]] = []
    if os.getenv("GEMINI_API_KEY", "").strip():
        providers.append({
            "id": "gemini",
            "name": "Gemini Live",
            "model": os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview"),
            "tier": "free-tier-eligible",
        })
    if os.getenv("OPENAI_API_KEY", "").strip():
        providers.append({
            "id": "openai",
            "name": "OpenAI Realtime",
            "model": os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime"),
            "tier": "paid",
        })
    return providers


def _upstream_config(provider: str) -> tuple[str, dict[str, str]]:
    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Gemini voice is not configured.")
        model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview").strip()
        url = (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
            f"?key={quote(api_key, safe='')}"
        )
        return url, {}
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OpenAI voice is not configured.")
        model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime").strip()
        return (
            f"wss://api.openai.com/v1/realtime?model={quote(model, safe='')}",
            {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"},
        )
    raise ValueError("Unsupported voice provider.")


@router.get("/api/voice/providers")
async def voice_providers() -> dict[str, object]:
    return {
        "providers": [
            {key: item[key] for key in ("id", "name", "model", "tier")}
            for item in available_voice_providers()
        ],
        "max_session_seconds": VOICE_SESSION_SECONDS,
    }


@router.websocket("/api/voice/{provider}")
async def voice_relay(websocket: WebSocket, provider: str) -> None:
    identity = _session_identity(websocket)
    if not identity:
        await websocket.close(code=4401, reason="Sign in required")
        return
    if identity in _active_sessions:
        await websocket.close(code=4409, reason="A voice session is already active")
        return
    try:
        upstream_url, headers = _upstream_config(provider)
    except ValueError as exc:
        await websocket.close(code=4400, reason=str(exc))
        return

    _active_sessions.add(identity)
    await websocket.accept()
    upstream = None
    try:
        upstream = await websockets.connect(
            upstream_url,
            additional_headers=headers,
            open_timeout=15,
            close_timeout=3,
            max_size=MAX_VOICE_MESSAGE_BYTES,
            ping_interval=20,
            ping_timeout=20,
        )

        async def client_to_provider() -> None:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                data = message.get("text")
                if data is None:
                    data = message.get("bytes")
                if data is None:
                    continue
                size = len(data.encode("utf-8")) if isinstance(data, str) else len(data)
                if size > MAX_VOICE_MESSAGE_BYTES:
                    await websocket.close(code=4400, reason="Voice message is too large")
                    return
                await upstream.send(data)

        async def provider_to_client() -> None:
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)

        tasks = {
            asyncio.create_task(client_to_provider()),
            asyncio.create_task(provider_to_client()),
        }
        timer = asyncio.create_task(asyncio.sleep(VOICE_SESSION_SECONDS))
        done, pending = await asyncio.wait(
            {*tasks, timer}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError, Exception):
                await task
        if timer in done:
            with suppress(Exception):
                await websocket.close(code=4408, reason="Voice session reached the 10-minute limit")
        for task in done:
            with suppress(WebSocketDisconnect, websockets.ConnectionClosed, Exception):
                task.result()
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        pass
    except Exception:
        with suppress(Exception):
            await websocket.close(code=1011, reason="Voice provider connection failed")
    finally:
        if upstream is not None:
            with suppress(Exception):
                await upstream.close()
        _active_sessions.discard(identity)
