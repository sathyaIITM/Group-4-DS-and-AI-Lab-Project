"""Scripted stand-ins for the model-backed and tool nodes, used without a model or data.

A stub returns the state update of its node as Section 4 contracts. The node that performs an
attempt increments its counter; the real nodes keep this behaviour. A stub follows
`RunConfig.stub_script[node]`, a list of values used in order (the last value repeats), or
`DEFAULTS[node]` when no script is given. The script position is kept in
`AnalystState.stub_positions`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from analyst.agents.events import stage_event
from analyst.agents.state import AnalystState
from analyst.contracts import (
    CellRef,
    CheckOutcome,
    CheckReport,
    Claim,
    ConfidenceResult,
    CoverageResult,
    DecisionRecord,
    IndicatorRef,
    InterpretationPlan,
    MissingPart,
    Narration,
    NumberCheck,
    NumberRef,
    PeriodWindow,
    QueryIntent,
    QueryResult,
    RoutingDecision,
    SqlAttempt,
    UnresolvedSlot,
    VerificationResult,
)
from analyst.contracts.results import ColumnSpec

DEFAULTS: dict[str, str] = {
    "route_tool_and_domain": "run_sql",
    "check_coverage": "covered",
    "validate_sql_with_sqlglot": "valid",
    "execute_read_only_duckdb": "success",
    "deterministic_result_checks": "pass",
    "verify_numbers_deterministically": "match",
    "verify_claim_support_and_intent": "skipped",
    "decide_answer_or_abstain": "answer",
}

STUB_DATASET = "stub_dataset"
STUB_SQL = "SELECT 1.0 AS value"

# Tool label -> branch before the rules of resolve_routing_decision are applied.
TOOL_BRANCH: dict[str, str] = {
    "run_sql": "query",
    "make_chart": "chart",
    "describe_table": "describe",
    "search_catalog": "search",
    "explain_result": "explain",
    "ask_clarification": "clarify",
    "decline_not_covered": "query",
}
# Old check-status words accepted in scripts, mapped to the Section 4 verdicts.
VERDICTS = {"empty": "empty_result", "absent": "data_absent"}


def next_script_value(state: AnalystState, node: str) -> tuple[Any, dict[str, int]]:
    """The next scripted value for `node` and the advanced script positions."""
    values = state.config.stub_script.get(node, [])
    if not values:
        return DEFAULTS.get(node, "pass"), state.stub_positions
    index = state.stub_positions.get(node, 0)
    value = values[min(index, len(values) - 1)]
    return value, {**state.stub_positions, node: index + 1}


def decision_record(decision: str, label: str, probability: float = 1.0) -> DecisionRecord:
    """Return a rules-backed decision record with one label."""
    return DecisionRecord(
        decision=decision,
        backend="rules",
        model_revision=None,
        label=label,
        probabilities={label: probability},
        calibrated=False,
        temperature=None,
        escalated=False,
        fallback=False,
        latency_ms=0,
        cost_usd=None,
    )


def stub_routing(tool: str, domain: str = "other", probability: float = 1.0) -> RoutingDecision:
    """Return a routing decision for the given tool and domain."""
    return RoutingDecision(
        tool=decision_record("tool", tool, probability),
        domain=decision_record("domain", domain, probability),
        final_tool=tool,
        final_domain=domain,
        branch=TOOL_BRANCH.get(tool, "query"),
    )


def stub_plan(dataset_id: str, unresolved: bool = False) -> InterpretationPlan:
    """Return a fixed plan for a dataset, optionally with an unresolved period."""
    slots = (
        [UnresolvedSlot(slot="period", mention="2019", options=["2018-19", "2019-20"])]
        if unresolved
        else []
    )
    return InterpretationPlan(
        dataset_id=dataset_id,
        obs_table=f"obs_{dataset_id}",
        dataset_version="stub",
        indicators=[IndicatorRef(indicator_id="stub_indicator", label="Stub", unit="unit")],
        places=[],
        all_places_level=None,
        periods=[
            PeriodWindow(
                requested="2010",
                type="calendar_year",
                label="2010",
                start=date(2010, 1, 1),
                end=date(2010, 12, 31),
            )
        ],
        categories={},
        operation="lookup",
        order=None,
        limit=None,
        derivations=[],
        exclude_total_rows=True,
        assumptions=[],
        unresolved=slots,
    )


def _dataset(state: AnalystState) -> str:
    """Return the first candidate dataset, or the default stub dataset."""
    if state.catalogue_candidates:
        return str(state.catalogue_candidates[0].get("dataset_id", STUB_DATASET))
    return STUB_DATASET


def _route(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub routing node update."""
    routing = stub_routing(str(value))
    return {"routing": routing, "decision_log": [routing.tool, routing.domain]}


def _intent(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub intent extraction node update."""
    intent = QueryIntent(
        action="answer",
        dataset_id=_dataset(state),
        indicator_ids=["stub_indicator"],
        place_mentions=[],
        all_places_level=None,
        period_mentions=["2010"],
        categories={},
        operation="lookup",
        order=None,
        limit=None,
        derivations=[],
        changed_slots=[],
        reason=None,
    )
    return {"intent": intent}


def _resolve(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub resolution node update."""
    dataset = state.intent.dataset_id if state.intent else _dataset(state)
    update: dict[str, Any] = {"plan": stub_plan(dataset, unresolved=value == "unresolved")}
    if state.plan is not None:  # re-entry after an empty result is a resolution retry
        update["counters"] = state.counters.bumped("resolution_retries")
    return update


def _coverage(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub coverage node update with the scripted status."""
    status = str(value)
    missing = [MissingPart(kind="indicator", detail="stub")] if status == "not_covered" else []
    coverage = CoverageResult(
        status=status,
        probability=None,
        decided_by="rules",
        missing=missing,
        supported_plan=state.plan if status == "partial" else None,
        left_out=["stub part"] if status == "partial" else [],
        pointers=[],
    )
    update: dict[str, Any] = {"coverage": coverage}
    if state.coverage is not None and state.checks is not None:  # re-check after data_absent
        update["counters"] = state.counters.bumped("coverage_rechecks")
    return update


def _restrict(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub restriction node update (no change)."""
    return {}


def _sql(kind: str) -> Callable[[AnalystState, Any], dict[str, Any]]:
    """Return a stub SQL node of the given kind."""

    def make(state: AnalystState, value: Any) -> dict[str, Any]:
        """Add a stub SQL attempt."""
        attempt = SqlAttempt(
            attempt=len(state.sql) + 1,
            kind=kind,
            sql=STUB_SQL,
            statement="Stub query",
            valid=True,
            error=None,
            executed_ms=None,
        )
        counter = "sql_repairs" if kind == "repair" else "sql_generations"
        return {"sql": [attempt], "counters": state.counters.bumped(counter)}

    return make


def _validate(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub SQL validation node update with the scripted result."""
    return {"validation_result": str(value)}


def _execute(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub execution node update with a one-value result."""
    result = QueryResult(
        sql=state.sql[-1].sql if state.sql else STUB_SQL,
        columns=[ColumnSpec(name="value", type="DOUBLE")],
        rows=[[1.0]],
        row_count=1,
        truncated=False,
        dataset_versions={state.plan.obs_table if state.plan else "obs_stub": "stub"},
        exec_ms=0,
    )
    return {"execution_result": str(value), "result": result}


def _derive(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub derivation node update (no derivations)."""
    return {"derived": []}


def _checks(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub result-check node update with the scripted verdict."""
    verdict = VERDICTS.get(str(value), str(value))
    passed = verdict in {"pass", "pass_with_caveats"}
    failure = "none" if verdict == "pass" else ("caveat" if passed else verdict)
    outcome = CheckOutcome(
        name="shape",
        passed=passed,
        failure_class=failure,
        expected=None,
        observed=None,
        detail="stub",
    )
    report = CheckReport(
        outcomes=[outcome],
        verdict=verdict,
        caveats=[],
        retry_hint=None if passed else "stub hint",
    )
    return {"checks": report}


def _narrate(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub narration node update."""
    number = NumberRef(text="1", cell=CellRef(row=0, column="value"), derived_id=None)
    narration = Narration(
        attempt=len(state.narration) + 1,
        text="The value is 1.",
        claims=[Claim(text="The value is 1.", numbers=[number])],
    )
    return {"narration": [narration], "counters": state.counters.bumped("narrations")}


def _numbers(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub number-check node update with the scripted result."""
    passed = value == "match"
    check = NumberCheck(
        passed=passed,
        matched=["1"] if passed else [],
        unmatched=[] if passed else ["1"],
        unit_or_direction_errors=[],
    )
    return {"number_check": check}


def _verify(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub verification node update."""
    numbers = state.number_check or NumberCheck(
        passed=True, matched=[], unmatched=[], unit_or_direction_errors=[]
    )
    skipped = value == "skipped"
    verification = VerificationResult(
        numbers=numbers,
        claims_supported=None if skipped else value == "supported",
        unsupported_claims=[] if skipped or value == "supported" else ["stub claim"],
        intent_aligned=None if skipped else value == "supported",
        misaligned_slots=[],
        score=None,
        skipped_reason="version" if skipped else None,
    )
    return {"verification": verification}


def _confidence(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub confidence node update (not verified)."""
    return {"confidence": ConfidenceResult(probability=None, badge="not_verified", inputs={})}


def _decide(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub answer-decision node update with the scripted decision."""
    return {"answer_decision": str(value), "answer_accepted": value == "answer"}


def _escalate(state: AnalystState, value: Any) -> dict[str, Any]:
    """Stub escalation node update (no change)."""
    return {}


STUBS: dict[str, Callable[[AnalystState, Any], dict[str, Any]]] = {
    "route_tool_and_domain": _route,
    "escalate_to_jev": _escalate,
    "extract_query_intent": _intent,
    "resolve_places_periods_units": _resolve,
    "check_coverage": _coverage,
    "define_supported_scope_and_caveats": _restrict,
    "generate_sql_with_hosted_llm": _sql("generate"),
    "bounded_sql_repair": _sql("repair"),
    "validate_sql_with_sqlglot": _validate,
    "execute_read_only_duckdb": _execute,
    "compute_derivations": _derive,
    "deterministic_result_checks": _checks,
    "narrate_from_result_only": _narrate,
    "verify_numbers_deterministically": _numbers,
    "verify_claim_support_and_intent": _verify,
    "calibrate_end_to_end_confidence": _confidence,
    "decide_answer_or_abstain": _decide,
}


def make_stub(node: str) -> Callable[[AnalystState], dict[str, Any]]:
    """A scripted node for `node`; unknown nodes only record their stage event."""
    build = STUBS.get(node)

    def run(state: AnalystState) -> dict[str, Any]:
        """Apply the next scripted value for this node."""
        value, positions = next_script_value(state, node)
        update = build(state, value) if build else {}
        update["stub_positions"] = positions
        update["events"] = stage_event(state, node, stub=True, script=str(value))
        return update

    run.__name__ = node
    return run
