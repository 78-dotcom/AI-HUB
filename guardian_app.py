from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

APP_VERSION = "0.1.0"
SCHEMA = "ai_guardian"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_TOKEN = os.getenv("GUARDIAN_ADMIN_TOKEN", "").strip()
MODEL_API_KEY = os.getenv("GUARDIAN_MODEL_API_KEY", "").strip()
MODEL_BASE_URL = os.getenv("GUARDIAN_MODEL_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
MODEL_NAME = os.getenv("GUARDIAN_MODEL", "openai/gpt-4.1-mini")
ENGINE: Engine | None = None
DB_MODE = "unconfigured"

app = FastAPI(title="AI Guardian", version=APP_VERSION, description="Independent evidence-based AI quality auditor")


def get_engine() -> Engine:
    global ENGINE, DB_MODE
    if ENGINE is not None:
        return ENGINE
    if DATABASE_URL:
        url = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        ENGINE = create_engine(url, pool_pre_ping=True, pool_recycle=300)
        DB_MODE = "postgres"
    else:
        # Temporary development fallback only. Render's filesystem is ephemeral.
        ENGINE = create_engine("sqlite:////tmp/ai_guardian_dev.db", connect_args={"check_same_thread": False})
        DB_MODE = "ephemeral_sqlite"
    return ENGINE


def initialize() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        if DB_MODE == "postgres":
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
            conn.execute(text(f'''
                CREATE TABLE IF NOT EXISTS "{SCHEMA}".audit_events (
                    event_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE
                )
            '''))
        else:
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    record_hash TEXT NOT NULL UNIQUE
                )
            '''))


def table_name() -> str:
    return f'"{SCHEMA}".audit_events' if DB_MODE == "postgres" else "audit_events"


def authorize(authorization: str | None = Header(default=None)) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Guardian is not configured: set GUARDIAN_ADMIN_TOKEN in Render.")
    supplied = authorization or ""
    expected = f"Bearer {ADMIN_TOKEN}"
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid Guardian token.")


class AuditRequest(BaseModel):
    project: str = Field(min_length=1, max_length=120)
    task_name: str = Field(min_length=1, max_length=200)
    run_id: str | None = Field(default=None, max_length=160)
    status: str = Field(default="unknown", max_length=40)
    summary: str = Field(default="", max_length=12000)
    claims: list[str] = Field(default_factory=list, max_length=100)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    previous_errors: list[str] = Field(default_factory=list, max_length=100)
    current_errors: list[str] = Field(default_factory=list, max_length=100)
    actions_claimed: list[str] = Field(default_factory=list, max_length=100)
    actions_confirmed: list[str] = Field(default_factory=list, max_length=100)


def deterministic_checks(payload: AuditRequest) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    status = payload.status.lower()
    if status not in {"completed", "success", "succeeded"}:
        checks.append({"severity": "warning", "code": "RUN_NOT_CONFIRMED", "message": "Задача не подтверждена как завершённая."})
    if not payload.evidence:
        checks.append({"severity": "warning", "code": "NO_EVIDENCE", "message": "Нет приложенных доказательств результата."})
    unconfirmed = sorted(set(payload.actions_claimed) - set(payload.actions_confirmed))
    if unconfirmed:
        checks.append({"severity": "error", "code": "UNCONFIRMED_ACTIONS", "message": "Заявлены действия без подтверждения: " + ", ".join(unconfirmed[:10])})
    repeated = sorted(set(payload.current_errors) & set(payload.previous_errors))
    if repeated:
        checks.append({"severity": "error", "code": "REPEATED_ERRORS", "message": "Повторяются ранее зарегистрированные ошибки: " + "; ".join(repeated[:10])})
    if payload.claims and not payload.evidence:
        checks.append({"severity": "warning", "code": "CLAIMS_WITHOUT_EVIDENCE", "message": "Есть утверждения, но нет подтверждающих материалов."})
    if not checks:
        checks.append({"severity": "info", "code": "BASIC_CHECKS_PASSED", "message": "Базовые структурные проверки пройдены; это не доказывает фактическую истинность утверждений."})
    return checks


async def model_critique(payload: AuditRequest, checks: list[dict[str, str]]) -> dict[str, Any]:
    if not MODEL_API_KEY:
        return {"status": "not_configured", "note": "Независимая модель-критик ещё не подключена; выполнены только программные проверки."}
    prompt = {
        "role": "system",
        "content": (
            "You are an independent auditor. Do not agree by default. Identify unsupported claims, "
            "missing evidence, contradictions, repeated failures and false completion claims. "
            "Never infer that a task completed without explicit evidence. Return concise JSON with "
            "keys verdict (pass/review/fail), findings (array of strings), and missing_evidence (array of strings)."
        ),
    }
    user = {"role": "user", "content": json.dumps({"audit": payload.model_dump(), "automated_checks": checks}, ensure_ascii=False)}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(35, connect=10)) as client:
            response = await client.post(
                f"{MODEL_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL_NAME, "messages": [prompt, user], "temperature": 0},
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise ValueError("Model returned no text")
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("Not an object")
            return {"status": "completed", "model": MODEL_NAME, "result": parsed}
        except json.JSONDecodeError:
            return {"status": "completed_unstructured", "model": MODEL_NAME, "result": content[:5000]}
    except Exception as exc:
        return {"status": "error", "model": MODEL_NAME, "note": f"Критик недоступен: {type(exc).__name__}. Программные проверки сохранены."}


def append_event(event: dict[str, Any]) -> dict[str, str]:
    initialize()
    engine = get_engine()
    table = table_name()
    with engine.begin() as conn:
        if DB_MODE == "postgres":
            conn.execute(text("SELECT pg_advisory_xact_lock(726381923)"))
        row = conn.execute(text(f"SELECT record_hash FROM {table} ORDER BY created_at DESC, event_id DESC LIMIT 1")).first()
        previous_hash = row[0] if row else "GENESIS"
        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256((previous_hash + "|" + event_id + "|" + created_at + "|" + canonical).encode("utf-8")).hexdigest()
        conn.execute(
            text(f"INSERT INTO {table} (event_id, created_at, event_json, previous_hash, record_hash) VALUES (:id, :created, :body, :prev, :digest)"),
            {"id": event_id, "created": created_at, "body": canonical, "prev": previous_hash, "digest": digest},
        )
    return {"event_id": event_id, "created_at": created_at, "previous_hash": previous_hash, "record_hash": digest}


@app.on_event("startup")
def startup() -> None:
    initialize()


@app.get("/")
def root() -> dict[str, Any]:
    return {"service": "AI Guardian", "version": APP_VERSION, "purpose": "Independent audit of AI work", "health": "/health", "audit_endpoint": "POST /v1/audits", "history_endpoint": "GET /v1/audits", "integrity_endpoint": "GET /v1/integrity"}


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        initialize()
        return {"status": "ok", "service": "AI Guardian", "version": APP_VERSION, "database": DB_MODE,
                "model_critic_configured": bool(MODEL_API_KEY), "admin_token_configured": bool(ADMIN_TOKEN)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database initialization failed: {type(exc).__name__}") from exc


@app.post("/v1/audits", dependencies=[Depends(authorize)])
async def create_audit(payload: AuditRequest) -> dict[str, Any]:
    checks = deterministic_checks(payload)
    critique = await model_critique(payload, checks)
    verdict = "fail" if any(item["severity"] == "error" for item in checks) else "review" if any(item["severity"] == "warning" for item in checks) else "provisional_pass"
    model_result = critique.get("result")
    if isinstance(model_result, dict):
        model_verdict = str(model_result.get("verdict", "")).lower()
        if model_verdict == "fail":
            verdict = "fail"
        elif model_verdict == "review" and verdict == "provisional_pass":
            verdict = "review"
    record = {
        "project": payload.project, "task_name": payload.task_name, "run_id": payload.run_id,
        "status": payload.status, "summary": payload.summary, "claims": payload.claims,
        "evidence": payload.evidence, "previous_errors": payload.previous_errors,
        "current_errors": payload.current_errors, "actions_claimed": payload.actions_claimed,
        "actions_confirmed": payload.actions_confirmed, "checks": checks,
        "model_critique": critique, "verdict": verdict,
    }
    chain = append_event(record)
    return {"verdict": verdict, "checks": checks, "model_critique": critique, "integrity": chain,
            "note": "provisional_pass означает только отсутствие обнаруженных проблем в доступных проверках, а не гарантию истинности."}


@app.get("/v1/audits", dependencies=[Depends(authorize)])
def list_audits(limit: int = 20) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")
    initialize()
    with get_engine().connect() as conn:
        rows = conn.execute(text(f"SELECT event_id, created_at, event_json, previous_hash, record_hash FROM {table_name()} ORDER BY created_at DESC, event_id DESC LIMIT :limit"), {"limit": limit}).all()
    return {"audits": [{"event_id": r[0], "created_at": r[1], "event": json.loads(r[2]), "previous_hash": r[3], "record_hash": r[4]} for r in rows]}


@app.get("/v1/integrity", dependencies=[Depends(authorize)])
def verify_integrity() -> dict[str, Any]:
    initialize()
    with get_engine().connect() as conn:
        rows = conn.execute(text(f"SELECT event_id, created_at, event_json, previous_hash, record_hash FROM {table_name()} ORDER BY created_at ASC, event_id ASC")).all()
    previous = "GENESIS"
    failures = []
    for row in rows:
        expected = hashlib.sha256((previous + "|" + row[0] + "|" + row[1] + "|" + row[2]).encode("utf-8")).hexdigest()
        if row[3] != previous or row[4] != expected:
            failures.append(row[0])
        previous = row[4]
    return {"integrity": "valid" if not failures else "tampering_or_corruption_detected",
            "records_checked": len(rows), "failed_event_ids": failures,
            "limitation": "Hash chaining detects edits/deletions in the chain, but a database owner with full write access could rewrite the entire chain."}
