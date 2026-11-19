"""Decision records and the routing decision (design document Section 4.7)."""

from typing import Literal

from analyst.contracts.common import Contract


class DecisionRecord(Contract):
    """One control decision: backend, label, probabilities, calibration, escalation and cost."""

    decision: Literal["tool", "domain", "coverage", "verification", "chart"]
    backend: Literal["kev", "jev", "laya", "llm", "rules"]
    model_revision: str | None
    label: str
    probabilities: dict[str, float]
    calibrated: bool
    temperature: float | None
    escalated: bool
    fallback: bool
    latency_ms: int
    cost_usd: float | None


class RoutingDecision(Contract):
    """The tool and domain decisions and the graph branch they select."""

    tool: DecisionRecord
    domain: DecisionRecord
    final_tool: str
    final_domain: str
    branch: Literal["query", "chart", "describe", "search", "explain", "clarify", "decline"]
