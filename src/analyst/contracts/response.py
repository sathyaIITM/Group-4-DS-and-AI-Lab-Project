"""What the caller receives (design document Section 4.7)."""

from typing import Literal

from analyst.contracts.chart import ChartSpec
from analyst.contracts.common import Contract

Outcome = Literal[
    "answered",
    "charted",
    "described",
    "searched",
    "explained",
    "clarifying",
    "declined",
    "abstained",
    "failed",
    "out_of_scope",
]
Cause = Literal[
    "not_covered",
    "not_comparable",
    "no_rows",
    "unverified",
    "low_confidence",
    "verifier_unavailable",
    "deadline_exceeded",
    "sql_invalid",
    "execution_error",
    "result_check_failed",
    "budget_exhausted",
    "backend_error",
]


class AgentResponse(Contract):
    run_id: str
    outcome: Outcome
    cause: Cause | None
    text: str
    badge: str | None
    evidence_id: str | None
    chart: ChartSpec | None
    options: list[str]
    pointers: list[str]
