"""Deterministic checks and the number check (design document Section 4.5)."""

from typing import Literal

from analyst.contracts.common import Caveat, Contract

FailureClass = Literal["none", "caveat", "query_fault", "empty_result", "data_absent"]


class CheckOutcome(Contract):
    """Result of one consistency check on a query result, with what was expected and observed."""

    name: str
    passed: bool
    failure_class: FailureClass
    expected: str | None
    observed: str | None
    detail: str


class CheckReport(Contract):
    """All check outcomes for a result, the overall verdict, caveats and a hint for a retry."""

    outcomes: list[CheckOutcome]
    verdict: Literal["pass", "pass_with_caveats", "query_fault", "empty_result", "data_absent"]
    caveats: list[Caveat]
    retry_hint: str | None


class NumberCheck(Contract):
    """Whether every number in the narration matches the result or a derived value."""

    passed: bool
    matched: list[str]
    unmatched: list[str]
    unit_or_direction_errors: list[str]
