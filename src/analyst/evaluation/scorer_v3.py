"""Scorer v3 for the end-to-end evaluation (Milestone 5).

Scorer v2 passes an answer when the expected values appear in the result and the narration. The
Milestone 4 review asked for checks of the interpretation, the completeness, the unit, the period
and the evidence as well. Each check below reads the execution record of a case (plan, result,
narration, evidence) and the structured gold fields of the item (`data/eval/README.md`, "Fields
added in Milestone 5"); none reads LLM judgements.

Every check returns True (pass), False (fail) or None (does not apply to the item). A case
succeeds when every check that applies passes. A record written before Milestone 5 lacks the
plan and evidence fields: `computable` is then False and the case cannot be scored under v3
(score it under v2 instead).

| Check | Applies to | Passes when |
| --- | --- | --- |
| action | all | the outcome matches `expected_action` |
| interpretation | answer | resolved places, periods and indicators match the gold (see below) |
| values | answer | scorer v2 values, narration and entity rule |
| completeness | answer | every expected value is narrated (a long series: ends and a chart) |
| unit | answer with a unit | the narration names the unit or a word for it |
| period | answer with periods | the narration names each period (a series: first, last) |
| evidence | answer | the evidence names a gold table, its source and the SQL |
| clarify_slot | clarify | asks for `clarify_slot`, more than one option, `clarify_options` |
| content | describe, search | the gold tables are named or retrieved (scorer v2 rule) |

Interpretation, corrected on 26 November 2026 after the first Milestone 5 test run of v2 showed
false failures (two general rules; every version, the dev sets and the Milestone 4 baseline are
scored with the corrected rules, and the report states the change): a plan with no place filter
matches a gold whose places are all national, since a national-only table needs no place (rule D);
a plan that holds a range as its two end points matches when the span contains every gold period
and the query result holds every expected value.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

CHECKS = (
    "action",
    "interpretation",
    "values",
    "completeness",
    "unit",
    "period",
    "evidence",
    "clarify_slot",
    "content",
)
ANSWER_OUTCOMES = {"answered", "charted"}
OUTCOMES = {
    "answer": ANSWER_OUTCOMES,
    "clarify": {"clarifying"},
    "decline": {"declined", "out_of_scope"},
    "describe": {"described"},
    "search": {"searched"},
}
# Words that name each catalogue unit in an answer. A unit without an entry (count) is not
# checked: a count needs no unit word.
UNIT_WORDS: dict[str, tuple[str, ...]] = {
    "percent": ("%", "percent", "per cent", "percentage"),
    "mm": ("mm", "millimetre", "millimeter"),
    "inr": ("₹", "rs", "rupee", "inr"),
    "inr_per_quintal": ("quintal",),
    "index_2012_100": ("index",),
    "per_1000_live_births": ("per 1,000", "per 1000", "per thousand"),
    "per_1000_males": ("per 1,000", "per 1000", "per thousand"),
    "births_per_1000_women": ("per 1,000", "per 1000", "per thousand"),
    "per_100000_population": ("per lakh", "per 100,000", "per 1,00,000", "per 100000"),
    "children_per_woman": ("per woman", "children"),
    "tonne": ("tonne", "ton"),
    "hectare": ("hectare", " ha"),
    "bale_170kg": ("bale",),
    "bale_180kg": ("bale",),
    "lakh": ("lakh",),
}
V3_RECORD_FIELDS = ("plan_places", "plan_periods", "plan_indicators", "evidence")
MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]  # fmt: skip


def _norm(text: Any) -> str:
    """Lower-case text with spacing and punctuation folded, for name comparison."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).strip()


def computable(case: dict[str, Any]) -> bool:
    """Return True when the record carries the fields scorer v3 reads."""
    return all(name in case for name in V3_RECORD_FIELDS)


def check_action(case: dict[str, Any]) -> bool:
    """The outcome matches the expected action."""
    return case.get("outcome") in OUTCOMES.get(str(case.get("expected_action")), set())


def check_interpretation(case: dict[str, Any], tolerance_match: Any = None) -> bool | None:
    """Resolved places, periods and indicators match the gold fields."""
    if case.get("expected_action") != "answer" or case.get("gold_lineage") is None:
        return None
    return _places_match(case) and _periods_match(case, tolerance_match) and _indicators_match(case)


def _places_match(case: dict[str, Any]) -> bool:
    """Explicit plan places equal the gold places; a whole level covers the gold places."""
    expected = case.get("expected_places") or []
    if not expected:
        return True
    planned = case.get("plan_places") or []
    if planned:
        return {_norm(p["name"]) for p in planned} == {_norm(p["name"]) for p in expected}
    level = case.get("plan_all_places_level")
    if level is None:
        # No place filter on a national-only gold: the table holds India only, and rule D
        # needs no place for it (corrected 26 November 2026; see the module docstring).
        return all(p.get("level") == "national" for p in expected)
    return all(p.get("level") == level for p in expected)


def _periods_match(case: dict[str, Any], tolerance_match: Any = None) -> bool:
    """Every gold period lies inside a planned window; no window means the full range.

    A plan may hold a range as its two end points ("from 2011 to 2016"). Such a plan matches
    when its span contains every gold period and the query result holds every expected value,
    so the whole range was read (corrected 26 November 2026).
    """
    expected = case.get("expected_periods") or []
    windows = case.get("plan_periods") or []
    if not expected or not windows:
        return True
    if all(
        any(w["start"] <= p["start"] and p["end"] <= w["end"] for w in windows) for p in expected
    ):
        return True
    span_start, span_end = min(w["start"] for w in windows), max(w["end"] for w in windows)
    if not all(span_start <= p["start"] and p["end"] <= span_end for p in expected):
        return False
    values = [float(v) for v in case.get("expected_values") or []]
    numbers = case.get("actual_numbers") or []
    tolerance = float(case.get("tolerance", 0.005))
    return (
        tolerance_match is not None
        and bool(values)
        and all(any(tolerance_match(n, v, tolerance) for n in numbers) for v in values)
    )


def _indicators_match(case: dict[str, Any]) -> bool:
    """The gold indicators are among the planned indicators."""
    expected = set(case.get("indicator_ids") or [])
    return expected <= set(case.get("plan_indicators") or [])


def check_completeness(case: dict[str, Any], tolerance_match: Any) -> bool | None:
    """Every expected value is narrated; a long series may give its end points with a chart."""
    if case.get("expected_action") != "answer":
        return None
    expected = [float(v) for v in case.get("expected_values") or []]
    if not expected:
        return None  # a value missing in the source: nothing to narrate
    narrated = case.get("narrated_numbers") or []
    tolerance = float(case.get("tolerance", 0.005))
    stated = [any(tolerance_match(n, e, tolerance) for n in narrated) for e in expected]
    if all(stated):
        return True
    return len(expected) > 3 and stated[0] and stated[-1] and bool(case.get("chart_attached"))


def check_unit(case: dict[str, Any]) -> bool | None:
    """The narration names the unit of the gold values."""
    if case.get("expected_action") != "answer" or not case.get("expected_values"):
        return None
    units = [u.strip() for u in str(case.get("unit") or "").split(";") if u.strip()]
    words = [UNIT_WORDS[u.casefold()] for u in units if u.casefold() in UNIT_WORDS]
    if not words:
        return None
    text = f" {str(case.get('response') or '').casefold()} "
    return all(any(word in text for word in group) for group in words)


def period_names(start: str, end: str) -> list[str]:
    """Ways an answer may name a period window (ISO start and end dates)."""
    first, last = date.fromisoformat(start[:10]), date.fromisoformat(end[:10])
    names: list[str] = []
    if first.year == last.year and first.month == last.month and first.day == 1:
        month = MONTHS[first.month - 1]
        names += [f"{month} {first.year}", f"{month[:3]} {first.year}", f"{first:%Y-%m}"]
    elif first.year == last.year:
        names.append(str(first.year))
    else:
        short = f"{last.year % 100:02d}"
        names += [
            f"{first.year}-{short}",
            f"{first.year}\u2013{short}",
            f"{first.year}-{last.year}",
        ]
        names += [f"{first.year} to {last.year}", f"{first.year}/{short}"]
        if (last.year - first.year) > 1:  # a multi-year window, such as 2019-21
            names.append(str(first.year))
    return names


def check_period(case: dict[str, Any]) -> bool | None:
    """The narration names each gold period (the first and last of a longer series)."""
    if case.get("expected_action") != "answer" or not case.get("expected_values"):
        return None
    periods = case.get("expected_periods") or []
    if not periods:
        return None
    if case.get("gold_lineage") == "inputs":
        periods = periods[:1]  # an aggregate over its input rows names its period once
    if len(periods) > 3:
        periods = [periods[0], periods[-1]]
    text = str(case.get("response") or "").casefold()
    return all(
        any(name.casefold() in text for name in period_names(p["start"], p["end"])) for p in periods
    )


def check_evidence(case: dict[str, Any]) -> bool | None:
    """The evidence names a gold table, its published source and the SQL."""
    if case.get("expected_action") != "answer":
        return None
    evidence = case.get("evidence") or {}
    tables = set(evidence.get("dataset_ids") or [])
    gold = set(case.get("dataset_ids") or [])
    return bool(tables & gold) and bool(evidence.get("has_source")) and bool(evidence.get("sql"))


def check_clarify_slot(case: dict[str, Any]) -> bool | None:
    """The clarifying question asks for the gold slot, with real options."""
    if case.get("expected_action") != "clarify" or case.get("outcome") != "clarifying":
        return None
    gold = case.get("clarify_slot")
    if gold is None:
        return None
    if gold not in (case.get("clarify_slots_asked") or []):
        return False
    options = [_norm(o) for o in case.get("clarify_options_asked") or []]
    if len(options) == 1:
        return False  # one option is an assumption, not a question (rule D10)
    wanted = [_norm(o) for o in case.get("clarify_options") or []]
    return all(any(w in o or o in w for o in options) for w in wanted)


def check_content(case: dict[str, Any], tables_named: Any) -> bool | None:
    """Describe and search name or retrieve the gold tables."""
    if case.get("expected_action") not in {"describe", "search"}:
        return None
    required = set(case.get("dataset_ids", []))
    retrieved = set(case.get("actual_dataset_ids", [])) | tables_named(case.get("response") or "")
    return required.issubset(retrieved)


def checks(
    case: dict[str, Any], values_ok: bool, tolerance_match: Any, tables_named: Any
) -> dict[str, bool | None]:
    """All v3 checks of one case. `values_ok` is the scorer v2 answer rule."""
    answer = case.get("expected_action") == "answer"
    return {
        "action": check_action(case),
        "interpretation": check_interpretation(case, tolerance_match),
        "values": values_ok if answer else None,
        "completeness": check_completeness(case, tolerance_match),
        "unit": check_unit(case),
        "period": check_period(case),
        "evidence": check_evidence(case),
        "clarify_slot": check_clarify_slot(case),
        "content": check_content(case, tables_named),
    }


def success(results: dict[str, bool | None]) -> bool:
    """A case succeeds when every check that applies passes."""
    return all(value is not False for value in results.values()) and results["action"] is True


def check_rates(per_case: list[dict[str, bool | None]]) -> dict[str, dict[str, Any]]:
    """Pass rate of each check over the cases it applies to."""
    rates: dict[str, dict[str, Any]] = {}
    for name in CHECKS:
        applied = [c[name] for c in per_case if c.get(name) is not None]
        rates[name] = {
            "n": len(applied),
            "pass_rate": sum(bool(v) for v in applied) / len(applied) if applied else None,
        }
    return rates
