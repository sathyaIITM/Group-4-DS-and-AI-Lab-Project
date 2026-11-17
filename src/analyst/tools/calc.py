"""Deterministic calculations kept outside generated SQL."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def pct_change(current: float, previous: float) -> float | None:
    """Return percentage change; undefined when the baseline is zero."""
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def change_pp(current: float, previous: float) -> float:
    """Difference between percentages, in percentage points."""
    return current - previous


def cagr(start: float, end: float, periods: int) -> float | None:
    """Compound annual growth rate in percent over positive endpoint values."""
    if periods <= 0:
        raise ValueError("periods must be positive")
    if start <= 0 or end < 0:
        return None
    return ((end / start) ** (1 / periods) - 1) * 100


def share(part: float, total: float) -> float | None:
    """Return part's share of total as a percentage."""
    return None if total == 0 else part / total * 100


def per_capita(value: float, population: float, scale: float = 1.0) -> float | None:
    """Return value per person, optionally scaling value (e.g. million currency)."""
    if population <= 0:
        return None
    return value * scale / population


def inflation_from_index(current: float, previous: float) -> float | None:
    """Calculate year-over-year inflation from index values, in percent."""
    return pct_change(current, previous)


def rank(values: Sequence[float], *, descending: bool = True) -> list[int]:
    """Return competition ranks (1, 1, 3) aligned with input order."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=descending)
    result = [0] * len(values)
    last: float | None = None
    current_rank = 0
    for position, index in enumerate(order, 1):
        if last is None or values[index] != last:
            current_rank = position
            last = values[index]
        result[index] = current_rank
    return result


def mean(values: Sequence[float], weights: Sequence[float] | None = None) -> float | None:
    """Arithmetic mean or weighted mean; zero total weight is undefined."""
    if not values:
        return None
    if weights is None:
        return sum(values) / len(values)
    if len(values) != len(weights):
        raise ValueError("values and weights must have equal lengths")
    denominator = sum(weights)
    return (
        None
        if denominator == 0
        else sum(v * w for v, w in zip(values, weights, strict=True)) / denominator
    )


def difference_is_clear(
    a: float,
    b: float,
    flags: Mapping[str, Any] | Sequence[str] | None = None,
    threshold: float = 0.05,
) -> bool:
    """Check whether two values differ by a meaningful relative amount.

    Caller-provided flags can explicitly mark comparisons as not comparable.
    """
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    if flags:
        blocked = {"not_comparable", "different_units", "different_periods", "different_population"}
        active = (
            {key for key, value in flags.items() if value}
            if isinstance(flags, Mapping)
            else set(flags)
        )
        if active & blocked:
            return False
    scale = max(abs(a), abs(b))
    if scale == 0:
        return False
    return abs(a - b) / scale >= threshold
