"""Deterministic, capability-aware model routing for AI HUB.

This module deliberately does not call providers. It selects from the server-side
catalogue and returns a safe public recommendation; execution stays in the chat
gateway until routing behavior is covered by tests and production telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TaskClassification:
    task: str
    required_capabilities: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RoutingDecision:
    task: str
    model_id: str
    alternatives: tuple[str, ...]
    reason: str


_TASK_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], str], ...] = (
    (
        "coding",
        ("code", "coding", "program", "programming", "debug", "python", "javascript",
         "typescript", "sql", "разработ", "программ", "код", "ошибк", "отлад"),
        ("code", "coding"),
        "The request appears to involve software development.",
    ),
    (
        "research",
        ("research", "sources", "citations", "compare", "latest", "investigate",
         "исслед", "источник", "ссылк", "сравн", "актуальн", "найди"),
        ("reasoning", "search"),
        "The request appears to require research or source evaluation.",
    ),
    (
        "document",
        ("document", "pdf", "spreadsheet", "contract", "report", "таблиц",
         "документ", "договор", "отчёт", "отчет", "файл", "pdf"),
        ("document", "vision"),
        "The request appears to involve document understanding.",
    ),
    (
        "creative",
        ("write a story", "creative", "script", "story", "poem", "design",
         "истори", "сценар", "стих", "придумай", "креатив"),
        ("creative",),
        "The request appears to involve creative generation.",
    ),
    (
        "business",
        ("business", "sales", "marketing", "customer", "lead", "proposal",
         "бизнес", "продаж", "маркет", "клиент", "заявк", "коммерческ"),
        ("business", "reasoning"),
        "The request appears to involve a business workflow.",
    ),
)


def classify_task(prompt: str) -> TaskClassification:
    """Classify a prompt using transparent, conservative keyword rules."""
    normalized = " ".join(prompt.lower().split())
    for task, keywords, capabilities, reason in _TASK_RULES:
        if any(keyword in normalized for keyword in keywords):
            return TaskClassification(task, capabilities, reason)
    return TaskClassification(
        "general", ("chat",), "No specialist task pattern was detected; use a general model."
    )


def _model_capabilities(model: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("capabilities", "input_modalities", "output_modalities"):
        raw = model.get(key, [])
        if isinstance(raw, (list, tuple, set)):
            values.update(str(item).strip().lower() for item in raw if str(item).strip())
    category = str(model.get("category", "")).strip().lower()
    if category:
        values.add(category)
    return values


def _score_model(
    model: Mapping[str, Any],
    classification: TaskClassification,
    preferred_model: str | None,
) -> tuple[int, str]:
    capabilities = _model_capabilities(model)
    score = 0
    matched = [capability for capability in classification.required_capabilities
               if capability in capabilities]
    score += len(matched) * 10

    task = classification.task
    category = str(model.get("category", "")).strip().lower()
    if category == task:
        score += 8
    if task == "general" and ("chat" in capabilities or not capabilities):
        score += 5
    if preferred_model and str(model.get("id", "")) == preferred_model:
        score += 3

    context_window = model.get("context_window")
    if isinstance(context_window, int) and not isinstance(context_window, bool) and context_window >= 32000:
        score += 1

    display_name = str(model.get("display_name") or model.get("model") or model.get("id") or "model")
    if matched:
        reason = f"Matches task capabilities: {', '.join(matched)}."
    elif category == task:
        reason = f"Model category matches the {task} task."
    else:
        reason = "Fallback candidate; no specialist capability was declared."
    return score, f"{display_name}: {reason}"


def select_model(
    models: Mapping[str, Mapping[str, Any]],
    prompt: str,
    preferred_model: str | None = None,
) -> RoutingDecision | None:
    """Return a deterministic routing decision, or None when no model is configured."""
    if not models:
        return None

    classification = classify_task(prompt)
    ranked: list[tuple[int, str, str]] = []
    for model_id, model in models.items():
        score, reason = _score_model(model, classification, preferred_model)
        ranked.append((score, model_id, reason))

    # Stable tie-breaking makes routing reproducible and testable.
    ranked.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_id, best_reason = ranked[0]
    if best_score == 0 and classification.task != "general":
        # Specialist task with no matching declarations: prefer general chat.
        general = [
            item for item in ranked
            if "chat" in _model_capabilities(models[item[1]])
            or str(models[item[1]].get("category", "")).lower() == "general"
        ]
        if general:
            general.sort(key=lambda item: (-item[0], item[1]))
            _, best_id, best_reason = general[0]
            best_reason = "No specialist match was declared; selected the best general fallback."
    alternatives = tuple(item[1] for item in ranked if item[1] != best_id)[:3]
    return RoutingDecision(
        task=classification.task,
        model_id=best_id,
        alternatives=alternatives,
        reason=f"{classification.reason} {best_reason}",
    )


def public_routing_payload(
    decision: RoutingDecision | None,
    models: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Serialize a routing decision without provider credentials or endpoints."""
    if decision is None:
        return {"available": False, "task": None, "selected_model": None, "alternatives": [], "reason": "No AI providers are configured."}

    def describe(model_id: str) -> dict[str, str]:
        model = models[model_id]
        return {
            "id": model_id,
            "name": str(model.get("display_name") or model.get("model") or model_id),
            "provider": str(model.get("provider_name") or model.get("provider") or ""),
        }

    return {
        "available": True,
        "task": decision.task,
        "selected_model": describe(decision.model_id),
        "alternatives": [describe(model_id) for model_id in decision.alternatives],
        "reason": decision.reason,
    }
