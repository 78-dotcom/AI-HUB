"""AI HUB Brain, Reality Check and Marketplace API foundations."""
from __future__ import annotations
import secrets
from datetime import datetime, timezone
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column
from accounts import Base, _db, account_user
from ai_council import MAX_COUNCIL_BUDGET_USD, MAX_OUTPUT_TOKENS_PER_MODEL, estimate_council_cost
from intelligence import public_routing_payload, select_model

router = APIRouter(prefix="/api", tags=["AI ecosystem"])

class MarketplaceAssistant(Base):
    __tablename__ = "marketplace_assistants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240), default="")
    instructions: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class BrainBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    preferred_model: str | None = Field(default=None, max_length=200)

class RealityCheckBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    lead_model: str = Field(min_length=1, max_length=200)
    reviewer_model: str = Field(min_length=1, max_length=200)
    reference_material: str = Field(default="", max_length=12000)
    budget_cap_usd: float = Field(default=0.25, gt=0, le=MAX_COUNCIL_BUDGET_USD)

class AssistantCreateBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=240)
    instructions: str = Field(min_length=10, max_length=6000)
    model_id: str | None = Field(default=None, max_length=200)
    is_public: bool = False

class AssistantRunBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    model_id: str | None = Field(default=None, max_length=200)

def _require_session(request: Request) -> None:
    from web_app import require_session
    require_session(request)

def _models() -> dict[str, dict[str, Any]]:
    from web_app import load_models
    return load_models()

def _account(request: Request) -> dict[str, str]:
    user = account_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="An individual account is required to publish assistants.")
    return user

def _text(data: dict[str, Any]) -> str:
    try:
        value = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Provider returned an unsupported response.") from exc
    if isinstance(value, list):
        value = "\n".join(str(part.get("text", "")) for part in value if isinstance(part, dict))
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Provider returned an empty response.")
    return value.strip()

async def _call(model: dict[str, Any], messages: list[dict[str, str]], max_tokens: int = 1200) -> tuple[str, dict[str, Any] | None]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(65.0, connect=15.0)) as client:
            response = await client.post(
                f'{model["base_url"]}/chat/completions',
                headers={"Authorization": f'Bearer {model["api_key"]}', "Content-Type": "application/json"},
                json={"model": model["model"], "messages": messages, "temperature": 0.25, "max_tokens": max_tokens},
            )
            response.raise_for_status()
            data = response.json()
        return _text(data), data.get("usage") if isinstance(data.get("usage"), dict) else None
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="The selected AI provider could not complete this request.") from exc

def _public(row: MarketplaceAssistant) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "description": row.description,
            "model_id": row.model_id, "is_public": row.is_public,
            "created_at": row.created_at.isoformat() if row.created_at else None}

_BUILT_INS = [
    {"id": "builtin-business-planner", "name": "Business Planner", "description": "Turns an idea into a practical business plan.", "category": "Business"},
    {"id": "builtin-writing-studio", "name": "Writing Studio", "description": "Creates and improves audience-aware writing.", "category": "Writing"},
    {"id": "builtin-learning-coach", "name": "Learning Coach", "description": "Explains difficult topics and builds learning steps.", "category": "Education"},
    {"id": "builtin-code-partner", "name": "Code Partner", "description": "Helps design, review and debug software.", "category": "Development"},
]

@router.post("/brain/run")
async def brain_run(body: BrainBody, request: Request) -> dict[str, Any]:
    _require_session(request)
    models = _models()
    decision = select_model(models, body.prompt, body.preferred_model)
    routing = public_routing_payload(decision, models)
    if not decision:
        raise HTTPException(status_code=503, detail="No AI providers are configured.")
    last_error = None
    for index, model_id in enumerate([decision.model_id, *decision.alternatives]):
        model = models.get(model_id)
        if not model or "text" not in model.get("input_modalities", ["text"]):
            continue
        try:
            answer, usage = await _call(model, [
                {"role": "system", "content": "You are AI HUB Brain. Solve the task directly. State uncertainty, separate facts from assumptions, and never invent sources."},
                {"role": "user", "content": body.prompt},
            ])
            return {"answer": answer, "task": routing["task"],
                    "selected_model": {"id": model_id, "name": model.get("display_name", model_id)},
                    "routing": routing, "fallback_used": index > 0,
                    "usage_reported": usage is not None,
                    "note": "Specialist routing with sequential fallback to another configured model."}
        except HTTPException as exc:
            last_error = exc
    raise last_error or HTTPException(status_code=503, detail="No compatible text model is available.")

@router.post("/reality-check/run")
async def reality_check(body: RealityCheckBody, request: Request) -> dict[str, Any]:
    _require_session(request)
    models = _models()
    lead, reviewer = models.get(body.lead_model), models.get(body.reviewer_model)
    if not lead or not reviewer or body.lead_model == body.reviewer_model:
        raise HTTPException(status_code=400, detail="Choose two different configured models.")
    for model in (lead, reviewer):
        if "text" not in model.get("input_modalities", ["text"]):
            raise HTTPException(status_code=400, detail="Reality Check currently supports text models.")
    try:
        estimate = estimate_council_cost(body.prompt + body.reference_material, lead, reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if estimate["estimated_max_cost_usd"] > body.budget_cap_usd:
        raise HTTPException(status_code=402, detail="Estimated cost exceeds your budget cap.")
    refs = "\n\nUSER-SUPPLIED MATERIAL (not independently authenticated):\n" + body.reference_material if body.reference_material else ""
    answer, _ = await _call(lead, [
        {"role": "system", "content": "Answer carefully. Mark uncertainty and do not invent citations."},
        {"role": "user", "content": body.prompt + refs},
    ], MAX_OUTPUT_TOKENS_PER_MODEL)
    audit_prompt = (
        "Audit the answer claim by claim. Return sections: SUPPORTED BY PROVIDED MATERIAL, "
        "UNSUPPORTED/UNCERTAIN, CONTRADICTIONS, MISSING CONTEXT, SAFER REWRITE. "
        "Do not claim external verification. If no references were supplied, state that this is only cross-model review.\n\n"
        f"QUESTION:\n{body.prompt}\n\nREFERENCE MATERIAL:\n{body.reference_material or '[none supplied]'}"
        f"\n\nPROPOSED ANSWER:\n{answer[:10000]}"
    )
    audit, _ = await _call(reviewer, [
        {"role": "system", "content": "You are the independent fact and logic auditor. Be skeptical, fair and precise."},
        {"role": "user", "content": audit_prompt},
    ], MAX_OUTPUT_TOKENS_PER_MODEL)
    return {"answer": answer, "audit": audit,
            "models": [lead.get("display_name", body.lead_model), reviewer.get("display_name", body.reviewer_model)],
            "estimated_max_cost_usd": estimate["estimated_max_cost_usd"], "budget_cap_usd": body.budget_cap_usd,
            "reference_material_provided": bool(body.reference_material.strip()),
            "verification_level": "cross_model_review_only",
            "note": "A second model review is not proof. External verification requires a connected search/retrieval tool."}

@router.get("/marketplace")
async def marketplace_list(request: Request) -> dict[str, Any]:
    _require_session(request)
    account = account_user(request)
    with _db() as db:
        rows = db.execute(select(MarketplaceAssistant).where(
            MarketplaceAssistant.is_public.is_(True) |
            (MarketplaceAssistant.owner_id == (account["id"] if account else "__none__"))
        ).order_by(MarketplaceAssistant.updated_at.desc()).limit(100)).scalars().all()
    return {
        "built_in": _BUILT_INS,
        "community": [
            {
                **_public(row),
                "can_edit": bool(account and row.owner_id == account["id"]),
                "instructions": row.instructions if account and row.owner_id == account["id"] else None,
            }
            for row in rows
        ],
    }

@router.post("/marketplace/assistants")
async def marketplace_create(body: AssistantCreateBody, request: Request) -> dict[str, Any]:
    account = _account(request)
    if body.model_id and (body.model_id not in _models() or "text" not in _models()[body.model_id].get("input_modalities", ["text"])):
        raise HTTPException(status_code=400, detail="The selected text model is not configured.")
    row = MarketplaceAssistant(id=secrets.token_urlsafe(18), owner_id=account["id"],
        name=body.name.strip(), description=body.description.strip(),
        instructions=body.instructions.strip(), model_id=body.model_id, is_public=body.is_public)
    with _db() as db:
        db.add(row)
        db.flush()
        return {"assistant": _public(row)}

@router.put("/marketplace/assistants/{assistant_id}")
async def marketplace_update(assistant_id: str, body: AssistantCreateBody, request: Request) -> dict[str, Any]:
    account = _account(request)
    if body.model_id and body.model_id not in _models():
        raise HTTPException(status_code=400, detail="The selected model is not configured.")
    with _db() as db:
        row = db.execute(select(MarketplaceAssistant).where(
            MarketplaceAssistant.id == assistant_id, MarketplaceAssistant.owner_id == account["id"]
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Assistant not found.")
        row.name, row.description, row.instructions = body.name.strip(), body.description.strip(), body.instructions.strip()
        row.model_id, row.is_public, row.updated_at = body.model_id, body.is_public, datetime.now(timezone.utc)
        return {"assistant": _public(row)}

@router.delete("/marketplace/assistants/{assistant_id}")
async def marketplace_delete(assistant_id: str, request: Request) -> dict[str, bool]:
    account = _account(request)
    with _db() as db:
        row = db.execute(select(MarketplaceAssistant).where(
            MarketplaceAssistant.id == assistant_id, MarketplaceAssistant.owner_id == account["id"]
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Assistant not found.")
        db.delete(row)
    return {"deleted": True}

@router.post("/marketplace/{assistant_id}/run")
async def marketplace_run(assistant_id: str, body: AssistantRunBody, request: Request) -> dict[str, Any]:
    _require_session(request)
    instructions, default_model, name = "", None, ""
    if assistant_id.startswith("builtin-"):
        preset = next((item for item in _BUILT_INS if item["id"] == assistant_id), None)
        if not preset:
            raise HTTPException(status_code=404, detail="Assistant not found.")
        name = preset["name"]
        instructions = {
            "builtin-business-planner": "Act as a practical small-business strategist. Give actionable steps, risks and metrics.",
            "builtin-writing-studio": "Act as an expert editor. Produce clear, polished writing and briefly explain key choices.",
            "builtin-learning-coach": "Teach step by step, adapt explanations and include a short practice exercise.",
            "builtin-code-partner": "Act as a senior software engineer. Explain trade-offs, test assumptions and provide safe code.",
        }[assistant_id]
    else:
        account = account_user(request)
        with _db() as db:
            row = db.execute(select(MarketplaceAssistant).where(
                MarketplaceAssistant.id == assistant_id,
                MarketplaceAssistant.is_public.is_(True) |
                (MarketplaceAssistant.owner_id == (account["id"] if account else "__none__"))
            )).scalar_one_or_none()
            if not row:
                raise HTTPException(status_code=404, detail="Assistant not found.")
            instructions, default_model, name = row.instructions, row.model_id, row.name
    models = _models()
    model_id = body.model_id or default_model
    if not model_id:
        decision = select_model(models, body.prompt)
        model_id = decision.model_id if decision else None
    model = models.get(model_id or "")
    if not model or "text" not in model.get("input_modalities", ["text"]):
        raise HTTPException(status_code=503, detail="Configure a compatible text model before running this assistant.")
    answer, _ = await _call(model, [
        {"role": "system", "content": instructions},
        {"role": "user", "content": body.prompt},
    ])
    return {"assistant": name, "model": model.get("display_name", model_id), "answer": answer}
