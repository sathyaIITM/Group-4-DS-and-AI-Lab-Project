from typing import Literal
from .common import Contract
class RoutingDecision(Contract):
    label: str = "run_sql"
    domain: str = "unspecified"
    probability: float = 1.0
    backend: str = "stub"
    escalated: bool = False
class DecisionRecord(Contract):
    decision: str
    backend: str = "stub"
    label: str | None = None
    probability: float | None = None
    escalated: bool = False
