from typing import Literal
from .common import Contract
Outcome = Literal["answered","charted","described","searched","explained","clarifying","declined","abstained","failed","out_of_scope"]
Cause = Literal["not_covered","not_comparable","no_rows","unverified","low_confidence","verifier_unavailable","deadline_exceeded","sql_invalid","execution_error","result_check_failed","budget_exhausted","backend_error"]
class AgentResponse(Contract):
    run_id: str
    outcome: Outcome
    text: str
    cause: Cause | None = None
    evidence_id: str | None = None
    chart: dict[str, object] | None = None
