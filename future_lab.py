"""Transparent scenario stress-testing primitives for AI HUB Future Lab.

This is a deterministic first layer, not a predictive world model. It only
projects user-supplied numeric assumptions and never invents probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScenarioVariable:
    name: str
    current_value: float
    downside_change_pct: float
    upside_change_pct: float
    unit: str = ""


def build_scenarios(
    objective: str,
    domain: str,
    horizon_months: int,
    variables: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build downside/base/upside stress cases from explicit user assumptions."""
    objective = " ".join(objective.split())
    domain = " ".join(domain.split()).lower()
    if not objective:
        raise ValueError("Objective is required.")
    if not domain:
        raise ValueError("Domain is required.")
    if not 1 <= horizon_months <= 120:
        raise ValueError("Horizon must be between 1 and 120 months.")
    if not 1 <= len(variables) <= 8:
        raise ValueError("Provide between 1 and 8 measurable variables.")

    parsed: list[ScenarioVariable] = []
    seen: set[str] = set()
    for raw in variables:
        if not isinstance(raw, dict):
            raise ValueError("Each variable must be an object.")
        name = " ".join(str(raw.get("name", "")).split())
        if not name or len(name) > 80 or name.lower() in seen:
            raise ValueError("Variable names must be unique and non-empty.")
        seen.add(name.lower())
        try:
            current = float(raw["current_value"])
            downside = float(raw["downside_change_pct"])
            upside = float(raw["upside_change_pct"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Each variable needs numeric values and change percentages.") from exc
        if not all(map(_finite, (current, downside, upside))):
            raise ValueError("Variable values must be finite numbers.")
        if not -1_000_000_000 <= current <= 1_000_000_000:
            raise ValueError("Current values are outside the supported range.")
        if not -100 <= downside <= 500 or not -100 <= upside <= 500:
            raise ValueError("Scenario changes must be between -100% and 500%.")
        unit = " ".join(str(raw.get("unit", "")).split())[:24]
        parsed.append(ScenarioVariable(name, current, downside, upside, unit))

    cases = []
    for key, title, field in (
        ("downside", "Downside stress case", "downside_change_pct"),
        ("base", "Baseline", None),
        ("upside", "Upside case", "upside_change_pct"),
    ):
        results = []
        for variable in parsed:
            change = 0.0 if field is None else getattr(variable, field)
            results.append({
                "name": variable.name,
                "current_value": variable.current_value,
                "change_pct": change,
                "projected_value": round(variable.current_value * (1 + change / 100), 4),
                "unit": variable.unit,
            })
        cases.append({"id": key, "title": title, "variables": results})

    return {
        "product": "AI HUB Future Lab",
        "mode": "assumption_stress_test",
        "objective": objective[:1000],
        "domain": domain[:80],
        "horizon_months": horizon_months,
        "scenarios": cases,
        "assumptions": [
            "Only the numeric assumptions supplied by the user were used.",
            "Changes are applied directly to the current values; interactions and time paths are not modelled.",
            "No probabilities, forecasts, or external facts are inferred.",
        ],
        "next_step": "Review the assumptions, then add evidence and domain-specific constraints before making a decision.",
    }


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
