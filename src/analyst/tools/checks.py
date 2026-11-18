"""Deterministic result and statistical checks tied to the resolved plan."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from analyst.contracts.checks import CheckOutcome, CheckReport, NumberCheck
from analyst.contracts.common import Caveat
from analyst.contracts.plan import InterpretationPlan
from analyst.contracts.results import QueryResult
from analyst.tools.numbers import verify_numbers


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
    matched = not required or required <= available or indicator_ids <= returned_ids
    outcomes.append(
        CheckOutcome(
            name="requested_indicators",
            passed=matched,
            failure_class="none" if matched else "query_fault",
            expected=", ".join(sorted(required | indicator_ids)) or None,
            observed=", ".join(sorted(available | returned_ids)),
            detail=(
                "Checks that requested measures are represented by result labels or indicator ids."
            ),
        )
    )
    outcomes.extend(run_intent_checks(plan, result))
    invalid = [item for item in derived if item.get("status") not in {None, "ok"}]
    outcomes.append(
        CheckOutcome(
            name="derived_values",
            passed=not invalid,
            failure_class="none" if not invalid else "query_fault",
            expected="all derivations defined",
            observed=f"{len(invalid)} undefined or incompatible",
            detail="Derived values must have compatible, reported inputs.",
        )
    )
    failures = [item for item in outcomes if not item.passed]
    verdict = (
        "empty_result"
        if any(item.failure_class == "empty_result" for item in failures)
        else "query_fault"
        if failures
        else "pass"
    )
    return CheckReport(
        outcomes=outcomes,
        verdict=verdict,
        caveats=[],
        retry_hint="Recheck period/place resolution and query predicates."
        if verdict in {"empty_result", "query_fault"}
        else None,
    )


def run_intent_checks(plan: InterpretationPlan, result: QueryResult) -> list[CheckOutcome]:
    """Check that selected geography and time filters are present in returned rows."""
    names = [column.name for column in result.columns]
    outcomes: list[CheckOutcome] = []
    if plan.places:
        place_columns = [i for i, name in enumerate(names) if name in {"geo_code", "geo_name"}]
        returned = {str(row[i]) for row in result.rows for i in place_columns}
        expected = {value for place in plan.places for value in (place.code, place.name)}
        matched = bool(returned & expected)
        outcomes.append(
            CheckOutcome(
                name="requested_places",
                passed=matched,
                failure_class="none" if matched else "query_fault",
                expected=", ".join(sorted(expected)),
                observed=", ".join(sorted(returned)),
                detail="Checks that a requested place is represented in the result.",
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
        matched = not period_columns or any(label in returned for label in expected)
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
