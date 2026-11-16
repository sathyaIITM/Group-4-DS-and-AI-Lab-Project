
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


# Shared frozen contracts. Keep state orchestration separate from module-boundary models.
from analyst.contracts import (
    ChartSpec, CheckReport, ConfidenceResult, CoverageResult, DecisionRecord,
    DerivedValue, EvidenceBundle, Event, InterpretationPlan, Narration,
    QueryIntent, QueryResult, RetryHint, RoutingDecision, SqlAttempt,
    VerificationResult,
)
from analyst.contracts.common import Clarification as PendingClarification
# from analyst.contracts.response import Outcome, Cause

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
    model_id: str = "unset"
    model_version: str = "unset"
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    config_hashes: dict[str, str] = Field(default_factory=dict)
    catalogue_contract_version: str = "unknown"

    @classmethod
    def from_files(cls, version: str = "v0", config_path: str = "configs/agent.yaml") -> "RunConfig":
        from analyst.config import load_run_config
        return load_run_config(version=version, config_path=config_path)


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
    response_text: str = ""
    answer_decision: str = "answer"
    validation_result: str = "valid"
    execution_result: str = "success"
    number_check_result: str = "match"
    chart_result: str = "unverified"
    requested_cause: str | None = None
    answer_accepted: bool = False
    finalized: bool = False
    run_log_path: str | None = None

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
    