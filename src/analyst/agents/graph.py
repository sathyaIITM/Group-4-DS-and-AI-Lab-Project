
# src/analyst/agents/graph.py

from __future__ import annotations

import time
from typing import Literal

from langgraph.graph import StateGraph, START, END

from analyst.agents.state import AnalystState
from analyst.agents.stubs import make_stub


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


def get_value(state, key, default=None):
    value = state.get(key, default)
    return value


def get_counter(state, name):
    counters = state.get("counters")
    if counters is None:
        return 0
    return getattr(counters, name, 0)


def get_limit(state, name):
    config = state.get("config")
    return getattr(config.limits, name)


def deadline_router(state, destination):
    """Central deadline check used by conditional routers."""

    started = state.get("started_at")
    config = state.get("config")

    if started is None:
        return destination

    elapsed = time.time() - started.timestamp()

    if elapsed > config.limits.run_deadline_s:
        return "abstain_with_reason"

    return destination


def finish_router(state):
    return END


def after_screen(state):
    if not state["screen"]["passes"]:
        return "respond_out_of_scope"

    return "retrieve_catalogue_candidates"


def after_routing(state):
    label = state["routing"].label

    mapping = {
        "run_sql": "retrieve_context_and_examples",
        "make_chart": "validate_existing_result_for_chart",
        "describe_table": "describe_from_metadata",
        "search_catalog": "search_catalog_entries",
        "explain_result": "explain_from_evidence",
        "ask_clarification": "ask_clarification",
        "decline_not_covered": "retrieve_context_and_examples",
    }

    if label == "explain_result" and not state.get("prior_result_ref"):
        return "search_catalog_entries"

    destination = mapping.get(label, "retrieve_context_and_examples")

    return deadline_router(state, destination)


def after_coverage(state):
    status = state["coverage"].status

    if status == "covered":
        return "generate_sql_with_hosted_llm"

    if status == "partial":
        return "define_supported_scope_and_caveats"

    if status == "ambiguous":
        return "ask_clarification"

    if status == "not_covered":
        count = get_counter(state, "widened_searches")
        limit = get_limit(state, "max_widened_searches")

        if count < limit:
            return "retrieve_context_and_examples"

        return "decline_and_log_data_request"

    return "report_system_failure"


def after_sql_validation(state):
    result = state.get("validation_result", "valid")

    if result == "valid":
        return "execute_read_only_duckdb"

    if get_counter(state, "sql_repairs") < get_limit(
        state, "max_sql_repairs"
    ):
        return "bounded_sql_repair"

    state["requested_cause"] = "sql_invalid"
    return "report_system_failure"


def after_execution(state):
    result = state.get("execution_result", "success")

    if result == "success":
        return "compute_derivations"

    if get_counter(state, "sql_generations") < get_limit(
        state, "max_sql_generations"
    ):
        return "generate_sql_with_hosted_llm"

    state["requested_cause"] = "execution_error"
    return "report_system_failure"


def after_checks(state):
    status = state["checks"].status

    if status == "pass":
        return "build_evidence_bundle"

    if status == "empty":
        if get_counter(state, "resolution_retries") < get_limit(
            state, "max_resolution_retries"
        ):
            return "resolve_places_periods_units"

        state["requested_cause"] = "no_rows"
        return "abstain_with_reason"

    if status == "absent":
        if get_counter(state, "coverage_rechecks") < get_limit(
            state, "max_coverage_rechecks"
        ):
            return "check_coverage"

        state["requested_cause"] = "no_rows"
        return "abstain_with_reason"

    if status == "query_fault":
        if get_counter(state, "sql_generations") < get_limit(
            state, "max_sql_generations"
        ):
            return "generate_sql_with_hosted_llm"

        state["requested_cause"] = "result_check_failed"
        return "report_system_failure"

    return "abstain_with_reason"


def after_number_check(state):
    result = state.get("number_check_result", "match")

    if result == "match":
        return "verify_claim_support_and_intent"

    if get_counter(state, "narrations") < get_limit(
        state, "max_narrations"
    ):
        return "narrate_from_result_only"

    state["requested_cause"] = "unverified"
    return "abstain_with_reason"


def after_claim_check(state):
    verification = state["verification"]

    if verification.claims_supported and verification.intent_aligned:
        return "calibrate_end_to_end_confidence"

    if get_counter(state, "narrations") < get_limit(
        state, "max_narrations"
    ):
        return "narrate_from_result_only"

    state["requested_cause"] = "unverified"
    return "abstain_with_reason"


def after_answer_decision(state):
    decision = state.get("answer_decision", "answer")

    if decision == "answer":
        return "assemble_answer_and_evidence_panel"

    state["requested_cause"] = "low_confidence"
    return "abstain_with_reason"


def after_chart_validation(state):
    if state.get("chart_result") == "verified":
        return "select_chart_type"

    return "ask_clarification"


def after_chart_render(state):
    return "finalize_response"


def build_graph():

    builder = StateGraph(AnalystState)

    # Register every node.
    for name in NODE_NAMES:
        builder.add_node(name, make_stub(name))

    # Intake.
    builder.add_edge(START, "receive_request")
    builder.add_edge("receive_request", "screen_request")

    builder.add_conditional_edges(
        "screen_request",
        after_screen,
    )

    # Routing.
    builder.add_edge(
        "retrieve_catalogue_candidates",
        "route_tool_and_domain",
    )

    builder.add_edge(
        "route_tool_and_domain",
        "resolve_routing_decision",
    )

    builder.add_conditional_edges(
        "resolve_routing_decision",
        after_routing,
    )

    # Chart, description, search and explanation.
    builder.add_conditional_edges(
        "validate_existing_result_for_chart",
        after_chart_validation,
    )

    builder.add_edge("describe_from_metadata", "finalize_response")
    builder.add_edge("search_catalog_entries", "finalize_response")
    builder.add_edge("explain_from_evidence", "finalize_response")

    # Retrieval and coverage.
    builder.add_edge(
        "retrieve_context_and_examples",
        "extract_query_intent",
    )
    builder.add_edge(
        "extract_query_intent",
        "resolve_places_periods_units",
    )
    builder.add_edge(
        "resolve_places_periods_units",
        "check_coverage",
    )

    builder.add_conditional_edges(
        "check_coverage",
        after_coverage,
    )

    builder.add_conditional_edges(
        "define_supported_scope_and_caveats",
        lambda state: "generate_sql_with_hosted_llm",
    )

    # SQL.
    builder.add_edge(
        "generate_sql_with_hosted_llm",
        "validate_sql_with_sqlglot",
    )

    builder.add_conditional_edges(
        "validate_sql_with_sqlglot",
        after_sql_validation,
    )

    builder.add_edge(
        "bounded_sql_repair",
        "validate_sql_with_sqlglot",
    )

    builder.add_conditional_edges(
        "execute_read_only_duckdb",
        after_execution,
    )

    builder.add_edge(
        "compute_derivations",
        "deterministic_result_checks",
    )

    builder.add_conditional_edges(
        "deterministic_result_checks",
        after_checks,
    )

    # Evidence and verification.
    builder.add_edge(
        "build_evidence_bundle",
        "narrate_from_result_only",
    )

    builder.add_edge(
        "narrate_from_result_only",
        "verify_numbers_deterministically",
    )

    builder.add_conditional_edges(
        "verify_numbers_deterministically",
        after_number_check,
    )

    builder.add_conditional_edges(
        "verify_claim_support_and_intent",
        after_claim_check,
    )

    builder.add_edge(
        "calibrate_end_to_end_confidence",
        "decide_answer_or_abstain",
    )

    builder.add_conditional_edges(
        "decide_answer_or_abstain",
        after_answer_decision,
    )

    # Output.
    builder.add_edge(
        "assemble_answer_and_evidence_panel",
        "select_chart_type",
    )

    builder.add_edge("select_chart_type", "render_chart")
    builder.add_edge("render_chart", "finalize_response")

    # Terminal branches.
    terminal_nodes = [
        "ask_clarification",
        "decline_and_log_data_request",
        "abstain_with_reason",
        "report_system_failure",
        "respond_out_of_scope",
    ]

    for node in terminal_nodes:
        builder.add_edge(node, "finalize_response")

    builder.add_edge("finalize_response", END)

    return builder.compile()