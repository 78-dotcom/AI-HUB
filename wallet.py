"""Read-only wallet views and append-only ledger primitives for HUB Credits.

No purchase, transfer, redemption, or public credit-issuance endpoint is exposed.
Only trusted payment reconciliation code may call record_credit_entry after it
has verified a provider event.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from accounts import Base, User, _db, account_user

router = APIRouter(prefix="/api/credits", tags=["HUB Credits"])


class CreditLedgerEntry(Base):
    __tablename__ = "credit_ledger_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_credit_user_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(40))
    delta_credits: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    reference_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def record_credit_entry(
    user_id: str,
    idempotency_key: str,
    event_type: str,
    delta_credits: Decimal,
    description: str = "",
    reference_id: str | None = None,
) -> str:
    """Append one verified ledger event; never update or delete prior entries."""
    if not user_id or not idempotency_key or len(idempotency_key) > 160:
        raise ValueError("A valid user and idempotency key are required.")
    if event_type not in {"purchase", "spend", "refund", "adjustment"}:
        raise ValueError("Unsupported ledger event type.")
    amount = Decimal(delta_credits)
    if not amount.is_finite() or amount == 0 or abs(amount) > Decimal("1000000000"):
        raise ValueError("Credit delta must be finite, non-zero, and within limits.")
    if event_type in {"purchase", "refund"} and amount < 0:
        raise ValueError("This event type must add credits.")
    if event_type == "spend" and amount > 0:
        raise ValueError("This event type must deduct credits.")
    entry_id = secrets.token_hex(16)
    try:
        with _db() as db:
            # Serialize postings per account on PostgreSQL so concurrent requests
            # cannot both spend the same available balance.
            owner = db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one_or_none()
            if owner is None:
                raise ValueError("HUB Credits account does not exist.")
            existing = db.execute(select(CreditLedgerEntry).where(
                CreditLedgerEntry.user_id == user_id,
                CreditLedgerEntry.idempotency_key == idempotency_key,
            )).scalar_one_or_none()
            if existing:
                return existing.id
            balance = db.execute(select(func.coalesce(func.sum(CreditLedgerEntry.delta_credits), 0)).where(
                CreditLedgerEntry.user_id == user_id
            )).scalar_one()
            if Decimal(balance or 0) + amount < 0:
                raise ValueError("Insufficient HUB Credits.")
            db.add(CreditLedgerEntry(
                id=entry_id, user_id=user_id, idempotency_key=idempotency_key,
                event_type=event_type, delta_credits=amount,
                reference_id=reference_id, description=description[:240],
            ))
        return entry_id
    except IntegrityError:
        # A concurrent duplicate webhook may win the unique-key race. Resolve it
        # by returning the already-posted row, never by adding a second credit.
        with _db() as db:
            existing = db.execute(select(CreditLedgerEntry).where(
                CreditLedgerEntry.user_id == user_id,
                CreditLedgerEntry.idempotency_key == idempotency_key,
            )).scalar_one_or_none()
            if existing:
                return existing.id
        raise


def _account(request: Request) -> dict[str, str]:
    user = account_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in with an individual AI HUB account.")
    return user


@router.get("/balance")
async def credits_balance(request: Request) -> dict[str, Any]:
    user = _account(request)
    with _db() as db:
        balance = db.execute(select(func.coalesce(func.sum(CreditLedgerEntry.delta_credits), 0)).where(
            CreditLedgerEntry.user_id == user["id"]
        )).scalar_one()
    return {
        "currency": "HUB_CREDITS",
        "balance": str(Decimal(balance or 0).quantize(Decimal("0.0001"))),
        "usd_reference_per_credit": "0.01",
        "usd_reference_is_redemption": False,
        "purchases_enabled": False,
        "transfers_enabled": False,
        "cash_redemption_enabled": False,
    }


@router.get("/ledger")
async def credits_ledger(request: Request, limit: int = 50) -> dict[str, list[dict[str, Any]]]:
    user = _account(request)
    limit = max(1, min(limit, 100))
    with _db() as db:
        rows = db.execute(select(CreditLedgerEntry).where(
            CreditLedgerEntry.user_id == user["id"]
        ).order_by(CreditLedgerEntry.created_at.desc()).limit(limit)).scalars().all()
    return {"entries": [{
        "id": row.id, "event_type": row.event_type,
        "delta_credits": str(row.delta_credits),
        "reference_id": row.reference_id, "description": row.description,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]}
