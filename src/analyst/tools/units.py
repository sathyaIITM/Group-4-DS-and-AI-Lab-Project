"""Exact unit conversion and Indian-style display helpers."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from analyst.contracts import Contract


class IncompatibleUnitsError(ValueError):
    """Raised when a requested conversion crosses incompatible unit dimensions."""


class ParsedNumber(Contract):
    """Numeric text extracted for evidence checking, with a conservative unit hint."""

    text: str
    value: Decimal
    unit_hint: str | None = None
    is_period: bool = False


_UNIT_ALIASES = {
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "quintal": "quintal",
    "quintals": "quintal",
    "qtl": "quintal",
    "tonne": "tonne",
    "tonnes": "tonne",
    "metric ton": "tonne",
    "metric tonne": "tonne",
    "thousand": "thousand",
    "thousands": "thousand",
    "lakh": "lakh",
    "lakhs": "lakh",
    "crore": "crore",
    "crores": "crore",
    "million": "million",
    "millions": "million",
    "inr": "inr",
    "rupee": "inr",
    "rupees": "inr",
    "₹": "inr",
    "lakh inr": "lakh_inr",
    "lakh rupees": "lakh_inr",
    "crore inr": "crore_inr",
    "crore rupees": "crore_inr",
    "%": "percent",
    "percent": "percent",
    "percentage": "percent",
    "percentage point": "percentage_point",
    "percentage points": "percentage_point",
    "pp": "percentage_point",
    "persons": "persons",
    "person": "persons",
}
_FACTORS: dict[str, tuple[str, Decimal]] = {
    "kg": ("mass", Decimal(1)),
    "quintal": ("mass", Decimal(100)),
    "tonne": ("mass", Decimal(1000)),
    "thousand": ("count", Decimal(1000)),
    "lakh": ("count", Decimal(100_000)),
    "crore": ("count", Decimal(10_000_000)),
    "million": ("count", Decimal(1_000_000)),
    "persons": ("count", Decimal(1)),
    "inr": ("money", Decimal(1)),
    "lakh_inr": ("money", Decimal(100_000)),
    "crore_inr": ("money", Decimal(10_000_000)),
}


def _unit(unit: str) -> str:
    key = re.sub(r"\s+", " ", unit.strip().casefold())
    return _UNIT_ALIASES.get(key, key.replace(" ", "_"))


def convert_unit(value: Decimal | int | float | str, from_unit: str, to_unit: str) -> Decimal:
    """Convert within mass, count, or INR dimensions; percent/points are never interchanged."""
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value: {value!r}") from exc
    source, target = _unit(from_unit), _unit(to_unit)
    if source == target:
        return number
    if source in {"percent", "percentage_point"} or target in {"percent", "percentage_point"}:
        raise IncompatibleUnitsError(f"cannot convert {from_unit} to {to_unit}")
    if source not in _FACTORS or target not in _FACTORS:
        raise IncompatibleUnitsError(f"unknown or incompatible unit: {from_unit} to {to_unit}")
    source_dimension, source_factor = _FACTORS[source]
    target_dimension, target_factor = _FACTORS[target]
    if source_dimension != target_dimension:
        raise IncompatibleUnitsError(f"cannot convert {from_unit} to {to_unit}")
    return number * source_factor / target_factor


def format_indian(value: Decimal | int | float | str, unit: str = "", decimals: int = 0) -> str:
    """Format a number with Indian digit grouping and an optional readable unit suffix."""
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    normalised = _unit(unit)
    if normalised in _FACTORS and _FACTORS[normalised][0] in {"count", "money"}:
        base_unit = "persons" if _FACTORS[normalised][0] == "count" else "inr"
        base_value = convert_unit(number, normalised, base_unit)
        if abs(base_value) >= Decimal(10_000_000):
            number = convert_unit(
                base_value, base_unit, "crore" if base_unit == "persons" else "crore_inr"
            )
            unit = "crore" if base_unit == "persons" else "crore INR"
            decimals = max(decimals, 2)
        elif abs(base_value) >= Decimal(100_000):
            number = convert_unit(
                base_value, base_unit, "lakh" if base_unit == "persons" else "lakh_inr"
            )
            unit = "lakh" if base_unit == "persons" else "lakh INR"
            decimals = max(decimals, 2)
    quantum = Decimal(1).scaleb(-decimals)
    rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
    negative = rounded < 0
    absolute = abs(rounded)
    fixed = f"{absolute:.{decimals}f}"
    whole, _, fraction = fixed.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while head:
            groups.append(head[-2:])
            head = head[:-2]
        whole = ",".join([*reversed(groups), tail])
    rendered = ("-" if negative else "") + whole + (f".{fraction}" if decimals else "")
    if _unit(unit) == "percent":
        return f"{rendered} percent"
    suffix = unit.strip()
    return f"{rendered} {suffix}".strip()


def display_decimals(unit: str, source_decimals: int | None = None) -> int:
    """Keep source precision for published values; use standard precision for derived values."""
    if source_decimals is not None:
        return max(0, source_decimals)
    normalised = _unit(unit)
    if normalised in {"percent", "percentage_point"}:
        return 1
    if normalised in {"inr", "lakh_inr", "crore_inr"}:
        return 2
    if normalised in {"persons", "thousand", "lakh", "crore", "million"}:
        return 0
    return 2


_NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<number>[+-]?(?:\d{1,3}(?:,\d{2})*,\d{3}|\d+)(?:\.\d+)?)"
    r"\s*(?P<unit>%|percent(?:age)?(?:\s+points?)?|pp|crores?|lakhs?|millions?|thousands?|"
    r"tonnes?|quintals?|qtl|kg|kilograms?|(?:lakh|crore)\s+(?:INR|rupees?)|INR|₹)?",
    re.IGNORECASE,
)
_PERIOD_RE = re.compile(r"\b(?:19|20)\d{2}\s*[-\u2013/]\s*\d{2,4}\b")


def parse_numbers(text: str) -> list[ParsedNumber]:
    """Extract numbers; protect year ranges from being treated as measurements."""
    period_matches = list(_PERIOD_RE.finditer(text))
    periods = [(match.start(), match.end()) for match in period_matches]
    positioned: list[tuple[int, ParsedNumber]] = [
        (
            match.start(),
            ParsedNumber(text=match.group(0), value=Decimal(match.group(0)[:4]), is_period=True),
        )
        for match in period_matches
    ]
    for match in _NUMBER_RE.finditer(text):
        if any(start < match.end() and match.start() < end for start, end in periods):
            continue
        raw = match.group("number")
        is_period = False
        unit = match.group("unit")
        unit_hint = _unit(unit) if unit else None
        try:
            parsed = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            continue
        positioned.append(
            (
                match.start(),
                ParsedNumber(
                    text=match.group(0).strip(),
                    value=parsed,
                    unit_hint=unit_hint,
                    is_period=is_period,
                ),
            )
        )
    return [item for _, item in sorted(positioned, key=lambda pair: pair[0])]
