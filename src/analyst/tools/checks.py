"""Deterministic result and statistical checks tied to the resolved plan."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from analyst.contracts.checks import CheckOutcome, CheckReport, NumberCheck
from analyst.contracts.common import Caveat
from analyst.contracts.plan import InterpretationPlan
from analyst.contracts.results import QueryResult
from analyst.tools.numbers import verify_numbers

NOT_IN_RESULT = "not in result: "  # prefix set by compute_derivations for missing rows


def run_result_checks(
    plan: InterpretationPlan, result: QueryResult, derived: Sequence[Mapping[str, Any]] = ()
) -> CheckReport:
    outcomes: list[CheckOutcome] = []
    if result.row_count == 0:
        outcomes.append(
            CheckOutcome(
                name="non_empty",
                passed=False,
                failure_class="empty_result",
                expected="at least one row",
                observed="0 rows",
                detail="The executed query returned no rows.",
            )
        )
    else:
        outcomes.append(
            CheckOutcome(
                name="non_empty",
                passed=True,
                failure_class="none",
                expected="at least one row",
                observed=str(result.row_count),
                detail="The executed query returned rows.",
            )
        )
    required = {indicator.label for indicator in plan.indicators}
    available = {column.name for column in result.columns}
    indicator_ids = {indicator.indicator_id for indicator in plan.indicators}
    id_column = next(
        (i for i, column in enumerate(result.columns) if column.name == "indicator_id"), None
    )
    returned_ids = {str(row[id_column]) for row in result.rows} if id_column is not None else set()
    checkable = id_column is not None or bool(required & available)
    matched = (
        not required or not checkable or required <= available or indicator_ids <= returned_ids
    )
    outcomes.append(
        CheckOutcome(
            name="requested_indicators",
            passed=matched,
            failure_class="none" if matched else "query_fault",
            expected=", ".join(sorted(required | indicator_ids)) or None,
            observed=", ".join(sorted(available | returned_ids)),
            detail=(
                "Checks that requested measures are represented by result labels or indicator ids."
                if checkable
                else "Not checkable: the result has no indicator column (single-measure query)."
            ),
        )
    )
    outcomes.extend(run_intent_checks(plan, result))
    # Design Section 4.5: an unreported input or an undefined value passes with a caveat;
    # incompatible inputs mean the data is absent; a derivation whose rows the query did not
    # return is a query fault (the query is retried with a hint).
    caveats: list[Caveat] = []
    faults, absent = [], []
    for item in derived:
        status, note = item.get("status"), str(item.get("note") or "")
        if status in {None, "ok"}:
            continue
        if note.startswith(NOT_IN_RESULT) or ": " + NOT_IN_RESULT in note:
            faults.append(item)
        elif status == "incompatible_inputs":
            absent.append(item)
        else:
            caveats.append(
                Caveat(
                    code=f"derivation_{status}",
                    text=f"{item.get('op')} could not be computed: {note}".strip(": "),
                    source="check",
                )
            )
    outcomes.append(
        CheckOutcome(
            name="derived_values",
            passed=not faults and not absent,
            failure_class="query_fault" if faults else "data_absent" if absent else "none",
            expected="every derivation input returned by the query",
            observed=f"{len(faults)} missing from the result, {len(absent)} incompatible, "
            f"{len(caveats)} not computable",
            detail="Derived values must have compatible, reported inputs.",
        )
    )
    failures = [item for item in outcomes if not item.passed]
    classes = {item.failure_class for item in failures}
    verdict: Literal["pass", "pass_with_caveats", "query_fault", "empty_result", "data_absent"]
    verdict = (
        "empty_result"
        if "empty_result" in classes
        else "query_fault"
        if "query_fault" in classes
        else "data_absent"
        if "data_absent" in classes
        else "pass_with_caveats"
        if caveats
        else "pass"
    )
    return CheckReport(
        outcomes=outcomes,
        verdict=verdict,
        caveats=caveats,
        retry_hint=_retry_hint(failures) if verdict in {"empty_result", "query_fault"} else None,
    )


def _retry_hint(failures: list[CheckOutcome]) -> str | None:
    """Name each failed check with what was expected and what the rows held."""
    faults = [f for f in failures if f.failure_class in {"query_fault", "empty_result"}]
    if not faults:
        return None
    parts = [
        f"{f.name}: expected {f.expected or 'rows'}; the rows held {f.observed or 'nothing'}"
        for f in faults
    ]
    return "Fix the query so that it returns what the checks need. " + "; ".join(parts)[:600]


def run_intent_checks(plan: InterpretationPlan, result: QueryResult) -> list[CheckOutcome]:
    """Check that selected geography and time filters are present in returned rows."""
    names = [column.name for column in result.columns]
    outcomes: list[CheckOutcome] = []
    if plan.places:
        own = {"geo_code", "geo_name", "entity"}
        by_level = {"state": own | {"geo_state"}, "district": own | {"geo_district"}}
        unmatched, checked, observed = [], 0, set()
        for place in plan.places:
            columns = [i for i, name in enumerate(names) if name in by_level.get(place.level, own)]
            if not columns:
                continue  # not checkable from the returned columns (aggregate query)
            checked += 1
            values = {str(row[i]) for row in result.rows for i in columns}
            observed |= values
            if not {place.code, place.name} & values:
                unmatched.append(place.name)
        outcomes.append(
            CheckOutcome(
                name="requested_places",
                passed=not unmatched,
                failure_class="query_fault" if unmatched else "none",
                expected=", ".join(sorted(p.name for p in plan.places)),
                observed=", ".join(sorted(observed))[:500],
                detail="Checks that each requested place is represented in the result."
                if checked
                else "Not checkable: the result has no place column (aggregate query).",
            )
        )
    if plan.periods:
        period_columns = [
            i
            for i, name in enumerate(names)
            if name in {"period_label", "period_start", "period_end", "year", "year_month"}
        ]
        returned = {
            str(result.rows[row_index][column_index])
            for row_index in range(len(result.rows))
            for column_index in period_columns
        }
        expected = {period.label for period in plan.periods}
        # A year asked of a monthly table is returned as its months ("2023" -> "2023-01").
        matched = not period_columns or any(
            label in returned or any(value.startswith(f"{label}-") for value in returned)
            for label in expected
        )
        outcomes.append(
            CheckOutcome(
                name="requested_periods",
                passed=matched,
                failure_class="none" if matched else "query_fault",
                expected=", ".join(sorted(expected)),
                observed=", ".join(sorted(returned)),
                detail="Checks that a requested period is represented in the result.",
            )
        )
    return outcomes


def run_statistical_checks(
    values: Sequence[float], *, expected_non_negative: bool = False
) -> list[dict[str, Any]]:
    """Flag non-finite values, negatives when forbidden, and extreme robust outliers."""
    numeric = [float(value) for value in values]
    findings: list[dict[str, Any]] = []
    for index, value in enumerate(numeric):
        if not math.isfinite(value):
            findings.append(
                {"index": index, "check": "finite", "passed": False, "value": str(value)}
            )
        elif expected_non_negative and value < 0:
            findings.append(
                {"index": index, "check": "non_negative", "passed": False, "value": value}
            )
    finite = [value for value in numeric if math.isfinite(value)]
    if len(finite) >= 4:
        ordered = sorted(finite)
        q1, q3 = ordered[len(ordered) // 4], ordered[(3 * len(ordered)) // 4]
        spread = q3 - q1
        if spread > 0:
            for index, value in enumerate(numeric):
                if math.isfinite(value) and (value < q1 - 3 * spread or value > q3 + 3 * spread):
                    findings.append(
                        {
                            "index": index,
                            "check": "extreme_outlier_review",
                            "passed": False,
                            "value": value,
                        }
                    )
    return findings


__all__ = [
    "Caveat",
    "NumberCheck",
    "run_intent_checks",
    "run_result_checks",
    "run_statistical_checks",
    "verify_numbers",
]
