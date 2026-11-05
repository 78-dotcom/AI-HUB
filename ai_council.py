"""Budget-aware primitives for the opt-in AI Council workflow."""

from __future__ import annotations

import math
from typing import Any, Mapping

MAX_OUTPUT_TOKENS_PER_MODEL = 800
MAX_COUNCIL_BUDGET_USD = 1.0


def _price(model: Mapping[str, Any], field: str) -> float:
    value = model.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("AI Council requires configured model pricing.")
    price = float(value)
    if not math.isfinite(price) or price < 0:
        raise ValueError("AI Council model pricing is invalid.")
    return price


def estimate_council_cost(prompt: str, lead: Mapping[str, Any], critic: Mapping[str, Any]) -> dict[str, Any]:
    """Conservative upper-bound estimate for two calls, using declared USD / 1M tokens."""
    lead_input_tokens = math.ceil(len(prompt) / 3)
    critic_prompt_chars = len(prompt) + MAX_OUTPUT_TOKENS_PER_MODEL * 4 + 500
    critic_input_tokens = math.ceil(critic_prompt_chars / 3)
    lead_cost = (
        lead_input_tokens * _price(lead, "input_cost_per_1m_usd")
        + MAX_OUTPUT_TOKENS_PER_MODEL * _price(lead, "output_cost_per_1m_usd")
    ) / 1_000_000
    critic_cost = (
        critic_input_tokens * _price(critic, "input_cost_per_1m_usd")
        + MAX_OUTPUT_TOKENS_PER_MODEL * _price(critic, "output_cost_per_1m_usd")
    ) / 1_000_000
    return {
        "estimated_max_cost_usd": round(lead_cost + critic_cost, 8),
        "lead_input_tokens_estimate": lead_input_tokens,
        "critic_input_tokens_estimate": critic_input_tokens,
        "max_output_tokens_per_model": MAX_OUTPUT_TOKENS_PER_MODEL,
        "model_calls": 2,
    }


def actual_cost_usd(usage: Any, model: Mapping[str, Any]) -> float | None:
    if not isinstance(usage, dict):
        return None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
               for v in (prompt_tokens, completion_tokens)):
        return None
    input_price = _price(model, "input_cost_per_1m_usd")
    output_price = _price(model, "output_cost_per_1m_usd")
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


def build_critic_prompt(task: str, proposed_answer: str) -> str:
    return (
        "Review the proposed answer critically. Identify factual or logical errors, "
        "missing assumptions, risks, and concrete improvements. Do not merely agree. "
        "If the answer is sound, say so and explain why. Do not invent sources.\n\n"
        f"USER TASK:\n{task}\n\nPROPOSED ANSWER:\n{proposed_answer[:12000]}"
    )
