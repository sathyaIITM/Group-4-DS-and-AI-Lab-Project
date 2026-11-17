"""Check narrated numbers against executed evidence, allowing only stated rounding."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from analyst.contracts.checks import NumberCheck
from analyst.tools.units import convert_unit, parse_numbers


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None


def verify_numbers(
    narration: str,
    evidence: list[Any] | dict[str, Any],
    *,
    relative_tolerance: Decimal = Decimal("0.005"),
    absolute_tolerance: Decimal = Decimal("0.01"),
) -> NumberCheck:
    """Require each non-period numeric claim to match a result or derived evidence value."""
    if relative_tolerance < 0 or absolute_tolerance < 0:
        raise ValueError("tolerances must be non-negative")
    raw_values = list(evidence.values()) if isinstance(evidence, dict) else list(evidence)
    supported = [number for value in raw_values if (number := _as_decimal(value)) is not None]
    matched: list[str] = []
    unmatched: list[str] = []
    for mention in parse_numbers(narration):
        if mention.is_period:
            continue
        mentioned_value = mention.value
        if mention.unit_hint in {"lakh", "crore", "million", "thousand", "persons"}:
            mentioned_value = convert_unit(mentioned_value, mention.unit_hint, "persons")
        elif mention.unit_hint in {"lakh_inr", "crore_inr", "inr"}:
            mentioned_value = convert_unit(mentioned_value, mention.unit_hint, "inr")
        elif mention.unit_hint in {"kg", "quintal", "tonne"}:
            mentioned_value = convert_unit(mentioned_value, mention.unit_hint, "kg")
        tolerance = max(absolute_tolerance, abs(mentioned_value) * relative_tolerance)
        if any(abs(mentioned_value - value) <= tolerance for value in supported):
            matched.append(mention.text)
        else:
            unmatched.append(mention.text)
    return NumberCheck(
        passed=not unmatched, matched=matched, unmatched=unmatched, unit_or_direction_errors=[]
    )
