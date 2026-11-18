"""The agent graph (design document Section 5, specification `agent_graph.md` v0.3).

Routers only choose the next node; they never write state. The cause of an abstention or a
failure is derived inside the terminal node (`nodes.failure_cause`, `nodes.abstention_cause`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from analyst.agents import nodes as t2
from analyst.agents.limits import budget_exhausted, deadline_exceeded
from analyst.agents.state import AnalystState
from analyst.agents.stubs import make_stub

RECURSION_LIMIT = 100

NODE_NAMES = [
    "receive_request",
    "screen_request",
    "retrieve_catalogue_candidates",
    "route_tool_and_domain",
    "escalate_to_jev",
    "resolve_routing_decision",
    "validate_existing_result_for_chart",
    "describe_from_metadata",
    "search_catalog_entries",
    "explain_from_evidence",
    "retrieve_context_and_examples",
    "extract_query_intent",
    "resolve_places_periods_units",
    "check_coverage",
    "define_supported_scope_and_caveats",
    "generate_sql_with_hosted_llm",
    "validate_sql_with_sqlglot",
    "bounded_sql_repair",
    "execute_read_only_duckdb",
    "compute_derivations",
    "deterministic_result_checks",
    "build_evidence_bundle",
    "narrate_from_result_only",
    "verify_numbers_deterministically",
    "verify_claim_support_and_intent",
    "calibrate_end_to_end_confidence",
    "decide_answer_or_abstain",
    "assemble_answer_and_evidence_panel",
    "select_chart_type",
    "render_chart",
    "ask_clarification",
    "decline_and_log_data_request",
    "abstain_with_reason",
    "report_system_failure",
    "respond_out_of_scope",
    "finalize_response",
]

# Nodes that call the hosted LLM; an edge into one of them is subject to the call budget.
LLM_NODES = {
    "route_tool_and_domain",
    "extract_query_intent",
    "generate_sql_with_hosted_llm",
    "bounded_sql_repair",
    "narrate_from_result_only",
    "ask_clarification",
}

# Nodes whose only edge leads to finalize_response; their edges are not guarded.
TERMINAL = {
    "describe_from_metadata",
    "search_catalog_entries",
    "explain_from_evidence",
    "render_chart",
    "ask_clarification",
    "decline_and_log_data_request",
    "abstain_with_reason",
    "report_system_failure",
    "respond_out_of_scope",
}

Router = Callable[[AnalystState], str]
NodeFn = Callable[[AnalystState], dict[str, Any]]


def guarded(router: Router) -> Router:
    """Apply the deadline and the LLM-call budget to an edge, exactly once."""

    def route(state: AnalystState) -> str:
        if state.node_error:
            return "report_system_failure"
        if not state.answer_accepted and deadline_exceeded(state):
            return "abstain_with_reason"
        destination = router(state)
        if destination in LLM_NODES and budget_exhausted(state):
            return "report_system_failure"
        return destination

    return route


def to(destination: str) -> Router:
    return lambda _state: destination


def after_screen(state: AnalystState) -> str:
    if state.screen is not None and not state.screen.passes:
        return "respond_out_of_scope"
    return "retrieve_catalogue_candidates"


BRANCH_NODES = {
    "query": "retrieve_context_and_examples",
    "chart": "validate_existing_result_for_chart",
    "describe": "describe_from_metadata",
    "search": "search_catalog_entries",
    "explain": "explain_from_evidence",
    "clarify": "ask_clarification",
    "decline": "decline_and_log_data_request",
}


def after_routing(state: AnalystState) -> str:
    branch = state.routing.branch if state.routing else "query"
    if branch == "explain" and not state.prior_result_ref:
        return "search_catalog_entries"
    return BRANCH_NODES.get(branch, "retrieve_context_and_examples")


def after_chart_validation(state: AnalystState) -> str:
    return "select_chart_type" if state.chart_result == "verified" else "ask_clarification"


def after_coverage(state: AnalystState) -> str:
    status = state.coverage.status if state.coverage else "covered"
    limits = state.config.limits
    if status == "covered":
        return "generate_sql_with_hosted_llm"
    if status == "partial":
        return "define_supported_scope_and_caveats"
    if status == "ambiguous":
        return "ask_clarification"
    if state.counters.widened_searches < limits.max_widened_searches and should_widen(state):
        return "retrieve_context_and_examples"
    return "decline_and_log_data_request"


def should_widen(state: AnalystState) -> bool:
    """Widen the search after not_covered only when it can help: the intent points to a table
    outside the candidates (intent v7, `catalogue_dataset_id`). An intent from an older prompt
    (`follow_up` None) keeps the earlier rule and widens on `none_fit` only. A named table with a
    missing period or place is never widened: more tables cannot supply that period."""
    intent = state.intent
    if intent is None:
        return True
    if intent.catalogue_dataset_id:
        return True
    return intent.follow_up is None and intent.dataset_id == "none_fit"


def after_sql_validation(state: AnalystState) -> str:
    if state.validation_result == "valid":
        return "execute_read_only_duckdb"
    if state.counters.sql_repairs < state.config.limits.max_sql_repairs:
        return "bounded_sql_repair"
    return "report_system_failure"


def after_execution(state: AnalystState) -> str:
    if state.execution_result == "success":
        return "compute_derivations"
    if state.counters.sql_generations < state.config.limits.max_sql_generations:
        return "generate_sql_with_hosted_llm"
    return "report_system_failure"


def after_checks(state: AnalystState) -> str:
    verdict = state.checks.verdict if state.checks else "pass"
    counters, limits = state.counters, state.config.limits
    if verdict in {"pass", "pass_with_caveats"}:
        return "build_evidence_bundle"
    if verdict == "empty_result":
        if counters.resolution_retries < limits.max_resolution_retries:
            return "resolve_places_periods_units"
        return "abstain_with_reason"
    if verdict == "data_absent":
        if counters.coverage_rechecks < limits.max_coverage_rechecks:
            return "check_coverage"
        return "abstain_with_reason"
    if counters.sql_generations < limits.max_sql_generations:  # query_fault
        return "generate_sql_with_hosted_llm"
    return "report_system_failure"


def after_number_check(state: AnalystState) -> str:
    if state.number_check is None or state.number_check.passed:
        return "verify_claim_support_and_intent"
    if state.counters.narrations < state.config.limits.max_narrations:
        return "narrate_from_result_only"
    return "abstain_with_reason"


def after_claim_check(state: AnalystState) -> str:
    v = state.verification
    supported = (
        v is None
        or v.skipped_reason is not None
        or (v.claims_supported is not False and v.intent_aligned is not False)
    )
    if supported:
        return "calibrate_end_to_end_confidence"
    if state.counters.narrations < state.config.limits.max_narrations:
        return "narrate_from_result_only"
    return "abstain_with_reason"


def after_answer_decision(state: AnalystState) -> str:
    if state.answer_decision == "answer":
        return "assemble_answer_and_evidence_panel"
    return "abstain_with_reason"


T2_NODES: dict[str, NodeFn] = {
    "receive_request": t2.receive_request,
    "screen_request": t2.screen_request,
    "retrieve_catalogue_candidates": t2.retrieve_catalogue_candidates,
    "resolve_routing_decision": t2.resolve_routing_decision,
    "validate_existing_result_for_chart": t2.validate_existing_result_for_chart,
    "describe_from_metadata": t2.describe_from_metadata,
    "search_catalog_entries": t2.search_catalog_entries,
    "explain_from_evidence": t2.explain_from_evidence,
    "retrieve_context_and_examples": t2.retrieve_context_and_examples,
    "build_evidence_bundle": t2.build_evidence_bundle,
    "assemble_answer_and_evidence_panel": t2.assemble_answer_and_evidence_panel,
    "select_chart_type": t2.select_chart_type,
    "render_chart": t2.render_chart,
    "ask_clarification": t2.ask_clarification,
    "decline_and_log_data_request": t2.decline_and_log_data_request,
    "abstain_with_reason": t2.abstain_with_reason,
    "report_system_failure": t2.report_system_failure,
    "respond_out_of_scope": t2.respond_out_of_scope,
    "finalize_response": t2.finalize_response,
}

# (source, router) pairs: conditional edges, all guarded.
CONDITIONAL: list[tuple[str, Router]] = [
    ("screen_request", after_screen),
    ("resolve_routing_decision", after_routing),
    ("validate_existing_result_for_chart", after_chart_validation),
    ("check_coverage", after_coverage),
    ("validate_sql_with_sqlglot", after_sql_validation),
    ("execute_read_only_duckdb", after_execution),
    ("deterministic_result_checks", after_checks),
    ("verify_numbers_deterministically", after_number_check),
    ("verify_claim_support_and_intent", after_claim_check),
    ("decide_answer_or_abstain", after_answer_decision),
]

# Plain edges; all but those leaving a terminal node are guarded.
PLAIN: list[tuple[str, str]] = [
    ("receive_request", "screen_request"),
    ("retrieve_catalogue_candidates", "route_tool_and_domain"),
    ("route_tool_and_domain", "escalate_to_jev"),
    ("escalate_to_jev", "resolve_routing_decision"),
    ("describe_from_metadata", "finalize_response"),
    ("search_catalog_entries", "finalize_response"),
    ("explain_from_evidence", "finalize_response"),
    ("retrieve_context_and_examples", "extract_query_intent"),
    ("extract_query_intent", "resolve_places_periods_units"),
    ("resolve_places_periods_units", "check_coverage"),
    ("define_supported_scope_and_caveats", "generate_sql_with_hosted_llm"),
    ("generate_sql_with_hosted_llm", "validate_sql_with_sqlglot"),
    ("bounded_sql_repair", "validate_sql_with_sqlglot"),
    ("compute_derivations", "deterministic_result_checks"),
    ("build_evidence_bundle", "narrate_from_result_only"),
    ("narrate_from_result_only", "verify_numbers_deterministically"),
    ("calibrate_end_to_end_confidence", "decide_answer_or_abstain"),
    ("assemble_answer_and_evidence_panel", "select_chart_type"),
    ("select_chart_type", "render_chart"),
    ("render_chart", "finalize_response"),
    ("ask_clarification", "finalize_response"),
    ("decline_and_log_data_request", "finalize_response"),
    ("abstain_with_reason", "finalize_response"),
    ("report_system_failure", "finalize_response"),
    ("respond_out_of_scope", "finalize_response"),
]


def build_graph(
    overrides: dict[str, NodeFn] | None = None,
) -> CompiledStateGraph[AnalystState, None, AnalystState, AnalystState]:
    """Compile the graph. `overrides` replaces stubs with real nodes by name."""
    builder = StateGraph(AnalystState)
    implementations = {**T2_NODES, **(overrides or {})}
    for name in NODE_NAMES:
        node: NodeFn = implementations.get(name) or make_stub(name)
        builder.add_node(name, node)  # type: ignore[call-overload]  # langgraph overloads
    builder.add_edge(START, "receive_request")
    for source, router in CONDITIONAL:
        builder.add_conditional_edges(source, guarded(router))
    for source, destination in PLAIN:
        if source not in TERMINAL:
            builder.add_conditional_edges(source, guarded(to(destination)))
        else:
            builder.add_edge(source, destination)
    builder.add_edge("finalize_response", END)
    return builder.compile()


def invoke_graph(state: AnalystState, overrides: dict[str, NodeFn] | None = None) -> AnalystState:
    """Run one request through the graph and return the final state."""
    final = build_graph(overrides).invoke(  # type: ignore[call-overload]
        state.model_dump(), config={"recursion_limit": RECURSION_LIMIT}
    )
    return AnalystState.model_validate(final)
