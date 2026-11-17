"""Graph state, run configuration, limits and counters (design document Section 4, note)."""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from analyst.contracts import (
    Cause,
    ChartSpec,
    CheckReport,
    Clarification,
    ConfidenceResult,
    CoverageResult,
    DecisionRecord,
    DerivedValue,
    Event,
    EvidenceBundle,
    InterpretationPlan,
    Narration,
    NumberCheck,
    Outcome,
    QueryIntent,
    QueryResult,
    RetryHint,
    RoutingDecision,
    ScreenResult,
    SqlAttempt,
    VerificationResult,
)
from analyst.decisions.kev_questions import KevState
from analyst.inference.llm import LlmCallRecord

__all__ = [
    "AnalystState",
    "Cause",
    "Counters",
    "Limits",
    "Outcome",
    "RagPaths",
    "RunConfig",
]


class Counters(BaseModel):
    """Attempt counters. The node that performs an attempt increments its counter."""

    sql_generations: int = 0
    sql_repairs: int = 0
    narrations: int = 0
    resolution_retries: int = 0
    coverage_rechecks: int = 0
    widened_searches: int = 0
    clarifications: int = 0
    llm_calls: int = 0

    def bumped(self, name: str) -> Counters:
        """A copy with counter `name` incremented by one."""
        return self.model_copy(update={name: getattr(self, name) + 1})


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
    # Thresholds are chosen on e2e_dev; None switches the rule that uses them off.
    candidate_min_score: float | None = None  # decline shortcut
    routing_floor: float | None = None  # not used by any rule (review item P8)
    shortcut_threshold: float | None = None  # decline and early-clarification shortcuts
    answer_threshold: float | None = None  # unused before v5


class RagPaths(BaseModel):
    """Guidance cards and verified examples; the v0 files are the fallback."""

    cards: str = "configs/rag/guidance_cards.v1.json"
    examples: str = "data/sample/rag_verified_examples.v1.jsonl"
    cards_fallback: str = "configs/rag/guidance_cards.v0.json"
    examples_fallback: str = "data/sample/rag_verified_examples.v0.jsonl"


class RunConfig(BaseModel):
    version: str = "v0"
    limits: Limits = Field(default_factory=Limits)
    rag: RagPaths = Field(default_factory=RagPaths)
    stub_script: dict[str, list[Any]] = Field(default_factory=dict)
    model_id: str = "unset"
    model_version: str = "unset"
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    config_hashes: dict[str, str] = Field(default_factory=dict)
    catalogue_contract_version: str = "unknown"

    @classmethod
    def from_files(cls, version: str = "v0", config_path: str = "configs/agent.yaml") -> RunConfig:
        from analyst.config import load_run_config

        return load_run_config(version=version, config_path=config_path)


class AnalystState(BaseModel):
    """LangGraph state. Contract-typed fields are None until the node that writes them runs."""

    run_id: str = ""
    conversation_id: str = ""
    question: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    pending_clarification: Clarification | None = None
    prior_result_ref: str | None = None
    prior_plan: InterpretationPlan | None = None
    prior_sql: str | None = None

    config: RunConfig = Field(default_factory=RunConfig)

    screen: ScreenResult | None = None
    catalogue_candidates: list[dict[str, Any]] = Field(default_factory=list)
    routing: RoutingDecision | None = None
    router_state: KevState | None = None  # what the router saw; escalation asks again with it
    retrieved: dict[str, Any] = Field(default_factory=dict)
    intent: QueryIntent | None = None
    plan: InterpretationPlan | None = None
    coverage: CoverageResult | None = None

    sql: Annotated[list[SqlAttempt], operator.add] = Field(default_factory=list)
    validation_result: str = "valid"
    execution_result: str = "success"
    result: QueryResult | None = None
    derived: list[DerivedValue] = Field(default_factory=list)
    checks: CheckReport | None = None
    retry_hints: Annotated[list[RetryHint], operator.add] = Field(default_factory=list)

    evidence: EvidenceBundle | None = None
    narration: Annotated[list[Narration], operator.add] = Field(default_factory=list)
    number_check: NumberCheck | None = None
    verification: VerificationResult | None = None
    confidence: ConfidenceResult | None = None
    answer_decision: str = "answer"
    answer_accepted: bool = False

    chart_result: str = "unverified"
    chart: ChartSpec | None = None

    response_text: str = ""
    requested_cause: Cause | None = None
    outcome: Outcome | None = None
    outcome_cause: Cause | None = None
    # Set by a node whose backend failed; the next edge ends the run in report_system_failure.
    node_error: Literal["backend_error", "budget_exhausted"] | None = None
    finalized: bool = False

    counters: Counters = Field(default_factory=Counters)
    events: Annotated[list[Event], operator.add] = Field(default_factory=list)
    decision_log: Annotated[list[DecisionRecord], operator.add] = Field(default_factory=list)
    llm_records: Annotated[list[LlmCallRecord], operator.add] = Field(default_factory=list)
    # Evaluation labels written to the run log: question_id, eval_set, experiment, member, turn.
    meta: dict[str, str | None] = Field(default_factory=dict)
    stub_positions: dict[str, int] = Field(default_factory=dict)
