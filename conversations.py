from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column

from accounts import Base, _db, account_user

router = APIRouter(prefix="/api", tags=["account data"])


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    selected_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    language: Mapped[str] = mapped_column(String(12), default="en")
    preferred_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    preferences_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    provider_id: Mapped[str] = mapped_column(String(100))
    model_id: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 8), default=Decimal("0"))
    request_status: Mapped[str] = mapped_column(String(24), default="succeeded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreferencesUpdate(BaseModel):
    language: str = Field(default="en", pattern="^(en|ru)$")
    preferred_model: str | None = Field(default=None, max_length=200)
    preferences: dict[str, Any] = Field(default_factory=dict)


def _require_account(request: Request) -> dict[str, str]:
    user = account_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in with an individual AI HUB account to sync your data.")
    return user


@router.get("/conversations")
async def list_conversations(request: Request) -> dict[str, list[dict[str, Any]]]:
    user = _require_account(request)
    with _db() as db:
        rows = db.execute(
            select(Conversation).where(
                Conversation.user_id == user["id"], Conversation.archived_at.is_(None)
            ).order_by(Conversation.updated_at.desc()).limit(100)
        ).scalars().all()
        if not rows:
            return {"conversations": []}
        message_rows = db.execute(
            select(Message).join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.user_id == user["id"],
                Conversation.id.in_([row.id for row in rows]),
            ).order_by(Message.created_at.asc(), Message.id.asc())
        ).scalars().all()
        grouped: dict[str, list[dict[str, str]]] = {row.id: [] for row in rows}
        for message in message_rows:
            grouped[message.conversation_id].append({
                "role": message.role, "content": message.content
            })
        return {"conversations": [
            {"id": row.id, "title": row.title, "selected_model": row.selected_model,
             "updated_at": row.updated_at.isoformat() if row.updated_at else None,
             "messages": grouped[row.id]}
            for row in rows
        ]}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    user = _require_account(request)
    with _db() as db:
        row = db.execute(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user["id"],
            Conversation.archived_at.is_(None)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        messages = db.execute(select(Message).where(
            Message.conversation_id == row.id
        ).order_by(Message.created_at.asc())).scalars().all()
        return {"conversation": {"id": row.id, "title": row.title,
            "selected_model": row.selected_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages]}}


@router.get("/preferences")
async def get_preferences(request: Request) -> dict[str, Any]:
    user = _require_account(request)
    with _db() as db:
        row = db.get(UserPreference, user["id"])
        if not row:
            return {"language": "en", "preferred_model": None, "preferences": {}}
        return {"language": row.language, "preferred_model": row.preferred_model,
                "preferences": row.preferences_json or {}}


@router.put("/preferences")
async def update_preferences(body: PreferencesUpdate, request: Request) -> dict[str, Any]:
    user = _require_account(request)
    with _db() as db:
        row = db.get(UserPreference, user["id"])
        if row is None:
            row = UserPreference(user_id=user["id"])
            db.add(row)
        row.language = body.language
        row.preferred_model = body.preferred_model
        row.preferences_json = body.preferences
        row.updated_at = func.now()
        return {"language": row.language, "preferred_model": row.preferred_model,
                "preferences": row.preferences_json}


@router.get("/usage")
async def get_usage(request: Request) -> dict[str, Any]:
    user = _require_account(request)
    with _db() as db:
        rows = db.execute(
            select(
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.input_tokens), 0),
                func.coalesce(func.sum(UsageEvent.output_tokens), 0),
            ).where(UsageEvent.user_id == user["id"], UsageEvent.request_status == "succeeded")
        ).one()
        recent = db.execute(
            select(UsageEvent).where(UsageEvent.user_id == user["id"])
            .order_by(UsageEvent.created_at.desc()).limit(20)
        ).scalars().all()
        return {
            "requests": int(rows[0] or 0),
            "input_tokens": int(rows[1] or 0),
            "output_tokens": int(rows[2] or 0),
            "estimated_cost_usd": None,
            "cost_note": "Provider pricing is not yet configured; costs are not estimated.",
            "recent": [{
                "provider": event.provider_id, "model": event.model_id,
                "input_tokens": event.input_tokens, "output_tokens": event.output_tokens,
                "status": event.request_status,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            } for event in recent],
        }


def persist_chat(request: Request, conversation_id: str | None, model_key: str,
                 messages: list[dict[str, str]], answer: str,
                 usage: dict[str, Any] | None = None) -> str | None:
    user = account_user(request)
    if not user:
        return None
    last_user = messages[-1]["content"]
    provider_id, _, model_id = model_key.partition(":")
    usage = usage or {}
    input_tokens = max(0, int(usage.get("prompt_tokens") or 0))
    output_tokens = max(0, int(usage.get("completion_tokens") or 0))
    with _db() as db:
        row = None
        if conversation_id:
            row = db.execute(select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user["id"],
                Conversation.archived_at.is_(None)
            )).scalar_one_or_none()
            if not row:
                raise HTTPException(status_code=404, detail="Conversation not found.")
        if row is None:
            row = Conversation(id=secrets.token_hex(16), user_id=user["id"],
                title=last_user[:200] or "New chat", selected_model=model_key)
            db.add(row)
            db.flush()
        else:
            row.selected_model = model_key
        message_time = datetime.now(timezone.utc)
        db.add(Message(id=secrets.token_hex(16), conversation_id=row.id,
            role="user", content=last_user, provider_id=provider_id, model_id=model_id,
            created_at=message_time))
        db.add(Message(id=secrets.token_hex(16), conversation_id=row.id,
            role="assistant", content=answer, provider_id=provider_id, model_id=model_id,
            input_tokens=input_tokens or None, output_tokens=output_tokens or None,
            created_at=message_time + timedelta(microseconds=1)))
        db.add(UsageEvent(
            id=secrets.token_hex(16), user_id=user["id"], conversation_id=row.id,
            provider_id=provider_id, model_id=model_id,
            input_tokens=input_tokens, output_tokens=output_tokens,
            estimated_cost_usd=Decimal("0"), request_status="succeeded",
        ))
        row.updated_at = func.now()
        return row.id
