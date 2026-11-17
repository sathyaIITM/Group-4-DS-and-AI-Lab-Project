"""Deterministic checks and the number check (design document Section 4.5)."""

from typing import Literal

from analyst.contracts.common import Caveat, Contract

FailureClass = Literal["none", "caveat", "query_fault", "empty_result", "data_absent"]


class CheckOutcome(Contract):
    name: str
    passed: bool
    failure_class: FailureClass
    expected: str | None
    observed: str | None
    detail: str


class CheckReport(Contract):
    outcomes: list[CheckOutcome]
    verdict: Literal["pass", "pass_with_caveats", "query_fault", "empty_result", "data_absent"]
    caveats: list[Caveat]
    retry_hint: str | None


class NumberCheck(Contract):
    passed: bool
    matched: list[str]
    unmatched: list[str]
    unit_or_direction_errors: list[str]
