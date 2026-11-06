from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
import threading
from contextlib import contextmanager
from typing import Iterator

from argon2 import PasswordHasher, exceptions as argon2_exceptions
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

ACCOUNT_COOKIE = "aihub_account_session"
ACCOUNT_TTL = 60 * 60 * 24 * 14
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_password_hasher = PasswordHasher()
_engines: dict[str, object] = {}
_schema_ready: set[int] = set()
_schema_lock = threading.Lock()
_auth_failures: dict[str, list[float]] = {}
_DUMMY_HASH = _password_hasher.hash("AI-HUB-invalid-account-placeholder")
router = APIRouter(prefix="/api/auth", tags=["accounts"])


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountSession(Base):
    __tablename__ = "account_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    invite_code: str = Field(min_length=1, max_length=256)


class AccountLoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _engine():
    url = _database_url()
    if not url:
        raise HTTPException(status_code=503, detail="Account storage is not configured yet.")
    if url not in _engines:
        options = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
            if url in {"sqlite://", "sqlite:///:memory:"}:
                options["poolclass"] = StaticPool
        _engines[url] = create_engine(url, **options)
    return _engines[url]


@contextmanager
def _db() -> Iterator[object]:
    engine = _engine()
    # Bootstrap the account tables once per process/engine, not on every request.
    # Production schema evolution still requires explicit versioned migrations.
    engine_key = id(engine)
    if engine_key not in _schema_ready:
        with _schema_lock:
            if engine_key not in _schema_ready:
                Base.metadata.create_all(engine)
                _schema_ready.add(engine_key)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _throttle_key(request: Request, action: str, limit: int = 5) -> str:
    host = request.client.host if request.client else "unknown"
    key = f"{action}:{host}"
    now = time.time()
    recent = [stamp for stamp in _auth_failures.get(key, []) if now - stamp < 900]
    _auth_failures[key] = recent
    if len(recent) >= limit:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait before trying again.")
    return key


def _record_auth_failure(key: str) -> None:
    _auth_failures.setdefault(key, []).append(time.time())


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_session(response: Response, user_id: str) -> None:
    token = secrets.token_urlsafe(48)
    with _db() as db:
        db.add(AccountSession(
            token_hash=_token_hash(token),
            user_id=user_id,
            expires_at=int(time.time()) + ACCOUNT_TTL,
        ))
    response.set_cookie(
        ACCOUNT_COOKIE,
        token,
        httponly=True,
        secure=bool(os.getenv("RENDER")),
        samesite="lax",
        max_age=ACCOUNT_TTL,
        path="/",
    )


def _current_user(request: Request):
    token = request.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return None
    with _db() as db:
        row = db.execute(
            select(User).join(AccountSession, AccountSession.user_id == User.id).where(
                AccountSession.token_hash == _token_hash(token),
                AccountSession.expires_at > int(time.time()),
            )
        ).scalar_one_or_none()
        return {"id": row.id, "email": row.email} if row else None


def account_user(request: Request):
    if not request.cookies.get(ACCOUNT_COOKIE) or not _database_url():
        return None
    return _current_user(request)


def revoke_account_session(request: Request, response: Response) -> None:
    token = request.cookies.get(ACCOUNT_COOKIE, "")
    if token and _database_url():
        with _db() as db:
            db.execute(AccountSession.__table__.delete().where(
                AccountSession.token_hash == _token_hash(token)
            ))
    response.delete_cookie(ACCOUNT_COOKIE, path="/", httponly=True, samesite="lax")


@router.get("/status")
async def account_status() -> dict[str, bool]:
    configured = bool(_database_url())
    return {
        "database_configured": configured,
        "registration_enabled": configured and bool(os.getenv("HUB_SIGNUP_CODE", "").strip()),
    }


@router.post("/register")
async def register(body: RegisterBody, request: Request, response: Response) -> dict[str, object]:
    attempt_key = _throttle_key(request, "register")
    invite = os.getenv("HUB_SIGNUP_CODE", "").strip()
    if not _database_url() or not invite:
        raise HTTPException(status_code=503, detail="Account registration is not enabled yet.")
    if not secrets.compare_digest(body.invite_code, invite):
        _record_auth_failure(attempt_key)
        raise HTTPException(status_code=403, detail="Invalid invitation code.")
    email = body.email.strip().lower()
    if not _EMAIL_RE.fullmatch(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    user_id = secrets.token_hex(16)
    try:
        with _db() as db:
            db.add(User(id=user_id, email=email, password_hash=_password_hasher.hash(body.password)))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    _auth_failures.pop(attempt_key, None)
    _set_session(response, user_id)
    return {"authenticated": True, "user": {"id": user_id, "email": email}}


@router.post("/login")
async def account_login(body: AccountLoginBody, request: Request, response: Response) -> dict[str, object]:
    attempt_key = _throttle_key(request, "login")
    if not _database_url():
        raise HTTPException(status_code=503, detail="Account storage is not configured yet.")
    email = body.email.strip().lower()
    with _db() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user:
            try:
                _password_hasher.verify(_DUMMY_HASH, body.password)
            except argon2_exceptions.VerificationError:
                pass
            _record_auth_failure(attempt_key)
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        try:
            valid = _password_hasher.verify(user.password_hash, body.password)
        except argon2_exceptions.VerificationError:
            valid = False
        if not valid:
            _record_auth_failure(attempt_key)
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        user_id = user.id
    _auth_failures.pop(attempt_key, None)
    _set_session(response, user_id)
    return {"authenticated": True, "user": {"id": user_id, "email": email}}


@router.get("/me")
async def account_me(request: Request) -> dict[str, object]:
    if not _database_url():
        raise HTTPException(status_code=503, detail="Account storage is not configured yet.")
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return {"authenticated": True, "user": user}


@router.post("/logout")
async def account_logout(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get(ACCOUNT_COOKIE, "")
    if token and _database_url():
        with _db() as db:
            db.execute(
                AccountSession.__table__.delete().where(
                    AccountSession.token_hash == _token_hash(token)
                )
            )
    response.delete_cookie(ACCOUNT_COOKIE, path="/", httponly=True, samesite="lax")
    return {"authenticated": False}
