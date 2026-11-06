
# src/analyst/agents/state.py

from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Outcome and cause types
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Placeholder models
# ---------------------------------------------------------

class PendingClarification(BaseModel):
    question: str = ""
    options: list[str] = Field(default_factory=list)


class InterpretationPlan(BaseModel):
    dataset_id: str | None = None
    indicator_id: str | None = None
    geography: dict = Field(default_factory=dict)
    period: dict = Field(default_factory=dict)
    unit: str | None = None
    filters: dict = Field(default_factory=dict)
    derivations: list[dict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class QueryIntent(BaseModel):
    dataset_id: str | None = None
    indicator_id: str | None = None
    place_mentions: list[str] = Field(default_factory=list)
    period_mentions: list[str] = Field(default_factory=list)
    categories: dict = Field(default_factory=dict)
    derivations: list[dict] = Field(default_factory=list)
    changed_slots: list[str] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    label: str = "run_sql"
    domain: str = "unspecified"
    probability: float = 1.0
    backend: str = "stub"
    escalated: bool = False


class CoverageResult(BaseModel):
    status: Literal[
        "covered", "partial", "ambiguous", "not_covered"
    ] = "covered"
    probability: float = 1.0
    decided_by: str = "stub"
    missing_parts: list[str] = Field(default_factory=list)
    supported_scope: str | None = None


class SqlAttempt(BaseModel):
    text: str = ""
    validation: str | None = None
    error: str | None = None


class QueryResult(BaseModel):
    rows: list[dict] = Field(default_factory=list)
    schema: list[dict] = Field(default_factory=list)
    dataset_version: str | None = None
    elapsed_ms: float = 0


class DerivedValue(BaseModel):
    operation: str = ""
    inputs: list[str] = Field(default_factory=list)
    output: float | None = None
    unit: str | None = None
    rounding: str | None = None
    status: Literal[
        "ok",
        "input_unreported",
        "undefined",
        "incompatible_inputs",
    ] = "ok"


class CheckReport(BaseModel):
    status: str = "pass"
    checks: dict = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    evidence_id: str = ""
    dataset_id: str | None = None
    dataset_version: str | None = None
    sql: str | None = None
    rows: list[dict] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class Narration(BaseModel):
    text: str = ""
    claims: list[dict] = Field(default_factory=list)


class VerificationResult(BaseModel):
    number_check: str = "match"
    claims_supported: bool = True
    intent_aligned: bool = True
    unsupported_claims: list[str] = Field(default_factory=list)
    misaligned_slots: list[str] = Field(default_factory=list)
    score: float = 1.0


class ConfidenceResult(BaseModel):
    probability: float | None = None
    badge_level: str = "not verified"
    inputs_used: dict = Field(default_factory=dict)


class ChartSpec(BaseModel):
    chart_type: str = "table"
    specification: dict = Field(default_factory=dict)


class Event(BaseModel):
    stage: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    details: dict = Field(default_factory=dict)


class DecisionRecord(BaseModel):
    decision: str
    backend: str = "stub"
    label: str | None = None
    probability: float | None = None
    escalated: bool = False


class RetryHint(BaseModel):
    stage: str
    reason: str
    change_required: str


# ---------------------------------------------------------
# Counters and limits
# ---------------------------------------------------------

class Counters(BaseModel):
    sql_generations: int = 0
    sql_repairs: int = 0
    narrations: int = 0
    resolution_retries: int = 0
    coverage_rechecks: int = 0
    widened_searches: int = 0
    clarifications: int = 0
    llm_calls: int = 0


class Limits(BaseModel):
    run_deadline_s: float = 30

    max_sql_generations: int = 3
    max_sql_repairs: int = 2
    max_narrations: int = 2
    max_resolution_retries: int = 1
    max_coverage_rechecks: int = 1
    max_widened_searches: int = 1
    max_clarifications: int = 2
    max_llm_calls: int = 8

    catalogue_top_k: int = 4

    candidate_min_score: float = 0.5
    routing_floor: float = 0.5
    shortcut_threshold: float = 0.9
    answer_threshold: float = 0.8


class RunConfig(BaseModel):
    version: str = "v0"
    limits: Limits = Field(default_factory=Limits)
    stub_script: dict[str, list] = Field(default_factory=dict)


# ---------------------------------------------------------
# Main graph state
# ---------------------------------------------------------

class AnalystState(BaseModel):

    run_id: str = ""
    conversation_id: str = ""
    question: str = ""

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    pending_clarification: PendingClarification | None = None
    prior_result_ref: str | None = None
    prior_plan: InterpretationPlan | None = None
    prior_sql: str | None = None

    config: RunConfig = Field(default_factory=RunConfig)

    screen: dict = Field(default_factory=lambda: {"passes": True})

    catalogue_candidates: list[dict] = Field(default_factory=list)
    routing: RoutingDecision = Field(default_factory=RoutingDecision)

    retrieved: dict = Field(default_factory=dict)
    intent: QueryIntent = Field(default_factory=QueryIntent)
    plan: InterpretationPlan = Field(default_factory=InterpretationPlan)

    coverage: CoverageResult = Field(default_factory=CoverageResult)

    sql: Annotated[list[SqlAttempt], operator.add] = Field(
        default_factory=list
    )

    result: QueryResult | None = None
    derived: list[DerivedValue] = Field(default_factory=list)

    checks: CheckReport = Field(default_factory=CheckReport)

    retry_hints: Annotated[list[RetryHint], operator.add] = Field(
        default_factory=list
    )

    evidence: EvidenceBundle | None = None

    narration: Annotated[list[Narration], operator.add] = Field(
        default_factory=list
    )

    verification: VerificationResult = Field(
        default_factory=VerificationResult
    )

    confidence: ConfidenceResult = Field(
        default_factory=ConfidenceResult
    )

    chart: ChartSpec | None = None

    outcome: Outcome | None = None
    outcome_cause: Cause | None = None

    counters: Counters = Field(default_factory=Counters)

    events: Annotated[list[Event], operator.add] = Field(
        default_factory=list
    )

    decision_log: Annotated[list[DecisionRecord], operator.add] = Field(
        default_factory=list
    )
    