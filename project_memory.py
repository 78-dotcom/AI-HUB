"""User-controlled project memory for AI HUB.

Entries are explicitly saved by the account owner. This module never mines chat
history or silently extracts personal information.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String, Text, func, select
from sqlalchemy.orm import Mapped, mapped_column

from accounts import Base, _db, account_user

router = APIRouter(prefix="/api/project-memory", tags=["project memory"])


class ProjectMemoryEntry(Base):
    __tablename__ = "project_memory_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_key: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40), default="decision")
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryCreate(BaseModel):
    project_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    category: str = Field(default="decision", min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=5000)


class MemoryUpdate(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=5000)


def _owner(request: Request) -> dict[str, str]:
    user = account_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in with an individual AI HUB account.")
    return user


def _serialize(row: ProjectMemoryEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_key": row.project_key,
        "category": row.category,
        "title": row.title,
        "content": row.content,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
async def list_project_memory(request: Request, project_key: str | None = None) -> dict[str, list[dict[str, Any]]]:
    user = _owner(request)
    with _db() as db:
        query = select(ProjectMemoryEntry).where(ProjectMemoryEntry.user_id == user["id"])
        if project_key:
            query = query.where(ProjectMemoryEntry.project_key == project_key)
        rows = db.execute(query.order_by(ProjectMemoryEntry.updated_at.desc()).limit(200)).scalars().all()
        return {"entries": [_serialize(row) for row in rows]}


@router.post("", status_code=201)
async def create_project_memory(body: MemoryCreate, request: Request) -> dict[str, Any]:
    user = _owner(request)
    with _db() as db:
        row = ProjectMemoryEntry(
            id=secrets.token_hex(16), user_id=user["id"],
            project_key=body.project_key, category=body.category.strip().lower(),
            title=body.title.strip(), content=body.content.strip(),
        )
        db.add(row)
        db.flush()
        return {"entry": _serialize(row)}


@router.put("/{entry_id}")
async def update_project_memory(entry_id: str, body: MemoryUpdate, request: Request) -> dict[str, Any]:
    user = _owner(request)
    with _db() as db:
        row = db.execute(select(ProjectMemoryEntry).where(
            ProjectMemoryEntry.id == entry_id, ProjectMemoryEntry.user_id == user["id"]
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Project memory entry not found.")
        row.category = body.category.strip().lower()
        row.title = body.title.strip()
        row.content = body.content.strip()
        row.updated_at = func.now()
        db.flush()
        return {"entry": _serialize(row)}


@router.delete("/{entry_id}")
async def delete_project_memory(entry_id: str, request: Request) -> dict[str, bool]:
    user = _owner(request)
    with _db() as db:
        row = db.execute(select(ProjectMemoryEntry).where(
            ProjectMemoryEntry.id == entry_id, ProjectMemoryEntry.user_id == user["id"]
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Project memory entry not found.")
        db.delete(row)
        return {"deleted": True}
