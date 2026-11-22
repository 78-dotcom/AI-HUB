from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/match-factor", tags=["Match-Factor"])
BASE_URL = "https://api.the-odds-api.com/v4"
_cache: dict[str, tuple[float, Any]] = {}
_usage: dict[str, int | None] = {
    "requests_remaining": None,
    "requests_used": None,
    "last_request_cost": None,
    "updated_at": None,
}
SPORTS_TTL = 60 * 60
ODDS_TTL = 90


def _require_session(request: Request) -> None:
    # Resolve at request time to avoid an import cycle with web_app.
    from web_app import require_session
    require_session(request)


def _api_key() -> str:
    return os.getenv("ODDS_API_KEY", "").strip()


def _cache_get(key: str, ttl: int) -> Any | None:
    item = _cache.get(key)
    if not item:
        return None
    created, value = item
    if time.time() - created > ttl:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


def _record_usage(headers: httpx.Headers) -> None:
    for header, field in (
        ("x-requests-remaining", "requests_remaining"),
        ("x-requests-used", "requests_used"),
        ("x-requests-last", "last_request_cost"),
    ):
        value = headers.get(header)
        if value is not None:
            try:
                _usage[field] = int(value)
            except ValueError:
                pass
    _usage["updated_at"] = int(time.time())


async def _get(path: str, params: dict[str, str]) -> Any:
    key = _api_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="The Odds API key is not configured. Add ODDS_API_KEY in Render environment settings.",
        )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            response = await client.get(f"{BASE_URL}{path}", params={**params, "apiKey": key})
        _record_usage(response.headers)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            message = "The Odds API rejected the key. Check ODDS_API_KEY in Render."
        elif status == 429:
            message = "The Odds API request limit has been reached. Check your plan and remaining credits."
        else:
            message = f"The Odds API returned HTTP {status}."
        raise HTTPException(status_code=502, detail=message) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not reach The Odds API. Please try again.") from exc


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    _require_session(request)
    return {
        "provider": "The Odds API",
        "configured": bool(_api_key()),
        "usage": _usage,
        "cache_seconds": ODDS_TTL,
    }


@router.get("/sports")
async def sports(request: Request) -> dict[str, Any]:
    _require_session(request)
    cached = _cache_get("sports", SPORTS_TTL)
    if cached is not None:
        return {"sports": cached, "cached": True}
    data = await _get("/sports", {"all": "false"})
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="The Odds API returned an unexpected sports list.")
    active = [
        {
            "key": item.get("key"),
            "title": item.get("title"),
            "group": item.get("group"),
            "active": item.get("active"),
        }
        for item in data
        if isinstance(item, dict) and item.get("active") and item.get("key")
    ]
    _cache_set("sports", active)
    return {"sports": active, "cached": False}


@router.get("/odds")
async def odds(
    request: Request,
    sport_key: str = Query(min_length=2, max_length=100),
    markets: str = Query(default="h2h", max_length=40),
) -> dict[str, Any]:
    _require_session(request)
    if not re.fullmatch(r"[a-zA-Z0-9_]+", sport_key):
        raise HTTPException(status_code=400, detail="Invalid sport key.")
    allowed = {"h2h", "spreads", "totals"}
    selected = list(dict.fromkeys(part.strip() for part in markets.split(",") if part.strip()))
    if not selected or len(selected) > 3 or any(market not in allowed for market in selected):
        raise HTTPException(status_code=400, detail="Markets must be h2h, spreads and/or totals.")
    market_arg = ",".join(selected)
    cache_key = f"odds:{sport_key}:eu:{market_arg}"
    cached = _cache_get(cache_key, ODDS_TTL)
    if cached is not None:
        return {"sport_key": sport_key, "markets": selected, "odds": cached, "cached": True, "usage": _usage}
    data = await _get(
        f"/sports/{sport_key}/odds",
        {"regions": "eu", "markets": market_arg, "oddsFormat": "decimal", "dateFormat": "iso"},
    )
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="The Odds API returned an unexpected odds response.")
    _cache_set(cache_key, data)
    return {"sport_key": sport_key, "markets": selected, "odds": data, "cached": False, "usage": _usage}
