from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from accounts import account_user, revoke_account_session, router as accounts_router
from conversations import persist_chat, router as conversations_router
from intelligence import public_routing_payload, select_model

load_dotenv()

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(APP_DIR, "web")
SESSION_COOKIE = "aihub_session"
SESSION_TTL = 60 * 60 * 24 * 7
MAX_HISTORY = 20
MAX_TEXT = 12000
LOGIN_WINDOW = 15 * 60
LOGIN_MAX_FAILURES = 5
_login_failures: dict[str, list[float]] = {}

app = FastAPI(title="AI HUB", version="0.2.0")
app.include_router(accounts_router)
app.include_router(conversations_router)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if os.getenv("RENDER"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def _login_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent_login_failures(key: str, now: float | None = None) -> list[float]:
    current = time.time() if now is None else now
    recent = [stamp for stamp in _login_failures.get(key, []) if current - stamp < LOGIN_WINDOW]
    if recent:
        _login_failures[key] = recent
    else:
        _login_failures.pop(key, None)
    return recent


def _expand_env(value: str) -> str:
    match = re.fullmatch(r"\$\{([A-Z0-9_]+)\}", value.strip())
    return os.getenv(match.group(1), "") if match else value


def load_models() -> dict[str, dict[str, Any]]:
    try:
        providers = json.loads(os.getenv("AI_PROVIDERS_JSON", "[]"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI_PROVIDERS_JSON must be valid JSON") from exc
    if not isinstance(providers, list):
        raise RuntimeError("AI_PROVIDERS_JSON must be a JSON array")

    if not providers and os.getenv("OPENROUTER_API_KEY", "").strip():
        providers = [{
            "id": "openrouter",
            "name": "OpenRouter",
            "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "api_key": "${OPENROUTER_API_KEY}",
            "models": [os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")],
        }]

    models: dict[str, dict[str, Any]] = {}
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        pid = str(provider.get("id", "")).strip()
        name = str(provider.get("name", pid)).strip()
        base = str(provider.get("base_url", "")).strip().rstrip("/")
        key = _expand_env(str(provider.get("api_key", ""))).strip()
        entries = provider.get("models", [])
        if not pid or not base or not key or not isinstance(entries, list):
            continue
        for item in entries:
            metadata = item if isinstance(item, dict) else {}
            model = str(metadata.get("id", metadata.get("model", "")) if metadata else item).strip()
            if not model:
                continue
            capabilities = metadata.get("capabilities", [])
            input_modalities = metadata.get("input_modalities", ["text"])
            output_modalities = metadata.get("output_modalities", ["text"])
            if not isinstance(capabilities, list):
                capabilities = []
            if not isinstance(input_modalities, list):
                input_modalities = ["text"]
            if not isinstance(output_modalities, list):
                output_modalities = ["text"]
            clean_strings = lambda values: list(dict.fromkeys(
                str(value).strip().lower() for value in values
                if isinstance(value, str) and value.strip()
            ))
            context_window = metadata.get("context_window")
            if not isinstance(context_window, int) or isinstance(context_window, bool) or context_window < 1:
                context_window = None
            models[f"{pid}:{model}"] = {
                "id": f"{pid}:{model}", "provider": pid, "provider_name": name,
                "model": model, "display_name": str(metadata.get("name", model)).strip() or model,
                "description": str(metadata.get("description", "")).strip()[:300],
                "category": str(metadata.get("category", "general")).strip().lower() or "general",
                "capabilities": clean_strings(capabilities),
                "input_modalities": clean_strings(input_modalities),
                "output_modalities": clean_strings(output_modalities),
                "context_window": context_window,
                "base_url": base, "api_key": key,
            }
    return models


def _extract_assistant_text(data: Any) -> str:
    """Normalize common OpenAI-compatible text response shapes."""
    if not isinstance(data, dict):
        raise ValueError("Invalid provider response")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Provider response has no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("Provider response has no assistant message")
    content = message.get("content")
    if isinstance(content, str):
        answer = content.strip()
    elif isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and part.get("type") in {"text", "output_text"}:
                value = part.get("text")
                if isinstance(value, str):
                    text_parts.append(value)
        answer = "".join(text_parts).strip()
    else:
        answer = ""
    if not answer:
        raise ValueError("Provider returned no text content")
    return answer


def _session_secret() -> str:
    return os.getenv("HUB_SESSION_SECRET", "").strip()


def _signature(payload: str) -> str:
    return hmac.new(_session_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_session() -> str:
    payload = base64.urlsafe_b64encode(str(int(time.time())).encode()).decode().rstrip("=")
    return f"{payload}.{_signature(payload)}"


def _valid_session(request: Request) -> bool:
    secret = _session_secret()
    token = request.cookies.get(SESSION_COOKIE, "")
    if not secret or "." not in token:
        return False
    payload, supplied = token.rsplit(".", 1)
    if not hmac.compare_digest(_signature(payload), supplied):
        return False
    try:
        issued = int(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode())
    except (ValueError, UnicodeDecodeError):
        return False
    age = int(time.time()) - issued
    return 0 <= age <= SESSION_TTL


def require_session(request: Request) -> None:
    if not _valid_session(request) and not account_user(request):
        raise HTTPException(status_code=401, detail="Please sign in to AI HUB.")


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ChatBody(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    messages: list[dict[str, str]] = Field(min_length=1, max_length=MAX_HISTORY)
    conversation_id: str | None = Field(default=None, max_length=36)


class RoutingBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_TEXT)
    preferred_model: str | None = Field(default=None, max_length=200)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "AI HUB"}


@app.get("/api/session")
async def session_status(request: Request) -> dict[str, bool]:
    return {"authenticated": _valid_session(request) or bool(account_user(request))}


@app.post("/api/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict[str, bool]:
    expected = os.getenv("HUB_ACCESS_PASSWORD", "")
    if not expected or not _session_secret():
        raise HTTPException(status_code=503, detail="AI HUB access is not configured yet.")
    key = _login_key(request)
    now = time.time()
    failures = _recent_login_failures(key, now)
    if len(failures) >= LOGIN_MAX_FAILURES:
        retry_after = max(1, int(LOGIN_WINDOW - (now - failures[0])))
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Please wait before trying again.",
            headers={"Retry-After": str(retry_after)},
        )
    if not hmac.compare_digest(body.password, expected):
        _login_failures[key] = [*failures, now]
        raise HTTPException(status_code=401, detail="Incorrect password.")
    _login_failures.pop(key, None)
    secure_cookie = bool(os.getenv("RENDER")) or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        SESSION_COOKIE, _make_session(), httponly=True, secure=secure_cookie,
        samesite="lax", max_age=SESSION_TTL, path="/",
    )
    return {"authenticated": True}


@app.post("/api/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    revoke_account_session(request, response)
    return {"authenticated": False}


@app.get("/api/models")
async def models(request: Request) -> dict[str, Any]:
    require_session(request)
    configured = load_models()
    public_models = [
        {
            key: item[key]
            for key in (
                "id", "provider", "provider_name", "model", "display_name",
                "description", "category", "capabilities", "input_modalities",
                "output_modalities", "context_window",
            )
        }
        for item in configured.values()
    ]
    return {"models": public_models, "default": os.getenv("DEFAULT_MODEL", "") or (public_models[0]["id"] if public_models else "")}


@app.post("/api/intelligence/route")
async def intelligence_route(body: RoutingBody, request: Request) -> dict[str, Any]:
    """Recommend a configured model for a task without executing a provider call."""
    require_session(request)
    configured = load_models()
    decision = select_model(configured, body.prompt, body.preferred_model)
    return public_routing_payload(decision, configured)


@app.post("/api/chat")
async def chat(body: ChatBody, request: Request) -> dict[str, str]:
    require_session(request)
    model = load_models().get(body.model)
    if not model:
        raise HTTPException(status_code=400, detail="That model is not configured.")
    messages: list[dict[str, str]] = []
    for item in body.messages[-MAX_HISTORY:]:
        role = item.get("role")
        content = item.get("content", "")
        if role not in {"user", "assistant"} or not isinstance(content, str) or len(content) > MAX_TEXT:
            raise HTTPException(status_code=400, detail="Invalid conversation message.")
        messages.append({"role": role, "content": content})
    if not messages or messages[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the user.")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(75.0, connect=15.0)) as client:
            result = await client.post(
                f'{model["base_url"]}/chat/completions',
                headers={"Authorization": f'Bearer {model["api_key"]}', "Content-Type": "application/json"},
                json={"model": model["model"], "messages": messages, "temperature": 0.7},
            )
            result.raise_for_status()
            data = result.json()
        answer = _extract_assistant_text(data)
        conversation_id = persist_chat(request, body.conversation_id, body.model, messages, answer, data.get("usage") if isinstance(data.get("usage"), dict) else None)
        return {"answer": answer, "conversation_id": conversation_id}
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise HTTPException(status_code=502, detail=f"AI provider returned HTTP {status}. Check the API key, model access and provider balance.") from exc
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not get a response from the AI provider. Please try again.") from exc
