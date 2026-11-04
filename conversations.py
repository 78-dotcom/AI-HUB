from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column

from accounts import Base, _db, account_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


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


class CreateConversation(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=200)
    selected_model: str | None = Field(default=None, max_length=200)


def _require_account(request: Request) -> dict[str, str]:
    user = account_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in with an individual AI HUB account to sync chat history.")
    return user


@router.get("")
async def list_conversations(request: Request) -> dict[str, list[dict[str, Any]]]:
    user = _require_account(request)
    with _db() as db:
        rows = db.execute(
            select(Conversation).where(
                Conversation.user_id == user["id"], Conversation.archived_at.is_(None)
            ).order_by(Conversation.updated_at.desc()).limit(100)
        ).scalars().all()
        return {"conversations": [
            {"id": row.id, "title": row.title, "selected_model": row.selected_model,
             "updated_at": row.updated_at.isoformat() if row.updated_at else None}
            for row in rows
        ]}


@router.get("/{conversation_id}")
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


def persist_chat(request: Request, conversation_id: str | None, model_key: str,
                 messages: list[dict[str, str]], answer: str) -> str | None:
    user = account_user(request)
    if not user:
        return None
    last_user = messages[-1]["content"]
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
        for item in messages[-2:]:
            db.add(Message(id=secrets.token_hex(16), conversation_id=row.id,
                role=item["role"], content=item["content"]))
        db.add(Message(id=secrets.token_hex(16), conversation_id=row.id,
            role="assistant", content=answer))
        row.updated_at = func.now()
        return row.id
