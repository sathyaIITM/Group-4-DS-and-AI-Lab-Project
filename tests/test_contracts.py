"""Every Section 4 contract has exactly the fields of the design document (01, Section 4).

A failure here means a contract was renamed, removed or added without a CONTRACT: change.
"""

import pytest
from pydantic import BaseModel, ValidationError

import analyst.contracts as c

SECTION_4: dict[type[BaseModel], set[str]] = {
    # 4.1
    c.Place: {"requested", "level", "code", "name", "match", "vintage"},
    c.PeriodWindow: {"requested", "type", "label", "start", "end", "default_applied"},
    c.IndicatorRef: {"indicator_id", "label", "unit"},
    c.CellRef: {"row", "column"},
    c.Assumption: {"code", "text"},
    c.Caveat: {"code", "text", "source"},
    # 4.2
    c.DerivationRequest: {"op", "args"},
    c.QueryIntent: {
        "action",
        "dataset_id",
        "indicator_ids",
        "place_mentions",
        "all_places_level",
        "period_mentions",
        "categories",
        "operation",
        "order",
        "limit",
        "derivations",
        "changed_slots",
        "reason",
        "missing_slot",
    },
    c.UnresolvedSlot: {"slot", "mention", "options"},
    c.InterpretationPlan: {
        "dataset_id",
        "obs_table",
        "dataset_version",
        "indicators",
        "places",
        "all_places_level",
        "periods",
        "categories",
        "operation",
        "order",
        "limit",
        "derivations",
        "exclude_total_rows",
        "assumptions",
        "unresolved",
    },
    # 4.3
    c.MissingPart: {"kind", "detail"},
    c.CoverageResult: {
        "status",
        "probability",
        "decided_by",
        "missing",
        "supported_plan",
        "left_out",
        "pointers",
    },
    # 4.4
    c.SqlDraft: {"sql", "statement"},
    c.SqlAttempt: {
        "attempt",
        "kind",
        "sql",
        "statement",
        "valid",
        "error_class",
        "error",
        "executed_ms",
    },
    c.ColumnSpec: {"name", "type"},
    c.QueryResult: {
        "sql",
        "columns",
        "rows",
        "row_count",
        "truncated",
        "dataset_versions",
        "exec_ms",
    },
    c.DerivedValue: {"id", "op", "inputs", "output", "unit", "decimals", "status", "note"},
    # 4.5
    c.CheckOutcome: {"name", "passed", "failure_class", "expected", "observed", "detail"},
    c.CheckReport: {"outcomes", "verdict", "caveats", "retry_hint"},
    c.NumberCheck: {"passed", "matched", "unmatched", "unit_or_direction_errors"},
    # 4.6
    c.SourceRef: {
        "dataset_id",
        "title",
        "publisher",
        "source_table",
        "licence",
        "retrieved",
        "dataset_version",
        "raw_sha256",
    },
    c.EvidenceBundle: {
        "evidence_id",
        "run_id",
        "question",
        "plan",
        "sources",
        "sql",
        "statement",
        "result",
        "derived",
        "checks",
        "assumptions",
        "caveats",
        "config_digest",
        "contract_version",
        "created_at",
    },
    c.NumberRef: {"text", "cell", "derived_id"},
    c.Claim: {"text", "numbers"},
    c.Narration: {"attempt", "text", "claims"},
    c.VerificationResult: {
        "numbers",
        "claims_supported",
        "unsupported_claims",
        "intent_aligned",
        "misaligned_slots",
        "score",
        "skipped_reason",
    },
    c.ConfidenceResult: {"probability", "badge", "inputs"},
    # 4.7
    c.DecisionRecord: {
        "decision",
        "backend",
        "model_revision",
        "label",
        "probabilities",
        "calibrated",
        "temperature",
        "escalated",
        "fallback",
        "latency_ms",
        "cost_usd",
    },
    c.RoutingDecision: {"tool", "domain", "final_tool", "final_domain", "branch"},
    c.ChartSpec: {"chart_type", "decided_by", "reason", "vega_lite"},
    c.Event: {"type", "run_id", "seq", "at", "stage", "payload"},
    c.AgentResponse: {
        "run_id",
        "outcome",
        "cause",
        "text",
        "badge",
        "evidence_id",
        "chart",
        "options",
        "pointers",
    },
}


@pytest.mark.parametrize("model", list(SECTION_4), ids=lambda m: m.__name__)
def test_fields_match_section_4(model: type[BaseModel]) -> None:
    assert set(model.model_fields) == SECTION_4[model]


@pytest.mark.parametrize("model", list(SECTION_4), ids=lambda m: m.__name__)
def test_contracts_are_frozen_and_closed(model: type[BaseModel]) -> None:
    assert model.model_config.get("frozen") is True
    assert model.model_config.get("extra") == "forbid"


def test_contract_version() -> None:
    assert c.CONTRACT_VERSION == "1.0"


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        c.CellRef(row=0, column="value", extra_field=1)  # type: ignore[call-arg]
