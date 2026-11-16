
# src/analyst/agents/stubs.py

from __future__ import annotations

from typing import Any

from analyst.agents.state import (
    Event,
    RoutingDecision,
    CoverageResult,
    QueryIntent,
    InterpretationPlan,
    CheckReport,
    VerificationResult,
    ConfidenceResult,
    QueryResult,
    EvidenceBundle,
    Narration,
    ChartSpec,
    SqlAttempt,
)


DEFAULTS = {
    "screen_request": "pass",
    "route_tool_and_domain": "run_sql",
    "resolve_routing_decision": "run_sql",
    "check_coverage": "covered",
    "validate_sql_with_sqlglot": "valid",
    "deterministic_result_checks": "pass",
    "verify_numbers_deterministically": "match",
    "verify_claim_support_and_intent": "supported",
    "decide_answer_or_abstain": "answer",
    "validate_existing_result_for_chart": "verified",
    "select_chart_type": "bar",
}


def next_script_value(state: dict, node_name: str) -> Any:
    """Read the next scripted result for a node."""

    config = state.get("config")

    if hasattr(config, "stub_script"):
        script = config.stub_script
    else:
        script = config.get("stub_script", {})

    values = script.get(node_name, [])

    if not values:
        return DEFAULTS.get(node_name, "pass")

    # Script position is stored in a private counter.
    positions = state.get("_stub_positions", {})
    index = positions.get(node_name, 0)

    value = values[min(index, len(values) - 1)]

    positions[node_name] = index + 1

    return value


def stage_event(node_name: str) -> list[Event]:
    return [Event(stage=node_name)]


def make_stub(node_name: str):
    """Create a simple scripted node."""

    def node(state: dict) -> dict:
        value = next_script_value(state, node_name)

        updates = {
            "_stub_positions": state.get("_stub_positions", {}),
            "events": stage_event(node_name),
        }

        if node_name == "screen_request":
            updates["screen"] = {
                "passes": value == "pass",
                "reason": None if value == "pass" else str(value),
            }

        elif node_name in (
            "route_tool_and_domain",
            "resolve_routing_decision",
        ):
            updates["routing"] = RoutingDecision(
                label=str(value),
                domain="unspecified",
                probability=1.0,
            )

        elif node_name == "retrieve_catalogue_candidates":
            updates["catalogue_candidates"] = [
                {"dataset_id": "stub_dataset", "score": 1.0}
            ]

        elif node_name == "retrieve_context_and_examples":
            updates["retrieved"] = {"entries": [], "examples": []}

        elif node_name == "extract_query_intent":
            updates["intent"] = QueryIntent(
                dataset_id="stub_dataset",
                indicator_id="stub_indicator",
            )

        elif node_name == "resolve_places_periods_units":
            updates["plan"] = InterpretationPlan(
                dataset_id="stub_dataset",
                indicator_id="stub_indicator",
            )

        elif node_name in ("check_coverage",):
            updates["coverage"] = CoverageResult(
                status=str(value)
            )

        elif node_name in (
            "generate_sql_with_hosted_llm",
            "bounded_sql_repair",
        ):
            updates["sql"] = [
                SqlAttempt(
                    text="SELECT 1 AS value",
                    validation=None,
                )
            ]

        elif node_name == "validate_sql_with_sqlglot":
            updates["validation_result"] = value

        elif node_name == "execute_read_only_duckdb":
            updates["execution_result"] = value
            updates["result"] = QueryResult(
                rows=[{"value": 1}],
                dataset_version="stub-v1",
            )

        elif node_name == "deterministic_result_checks":
            updates["checks"] = CheckReport(status=str(value))

        elif node_name == "build_evidence_bundle":
            updates["evidence"] = EvidenceBundle(
                evidence_id="stub-evidence",
                dataset_id="stub_dataset",
                dataset_version="stub-v1",
                sql="SELECT 1 AS value",
                rows=[{"value": 1}],
            )

        elif node_name == "narrate_from_result_only":
            updates["narration"] = [
                Narration(
                    text="The result is 1.",
                    claims=[{"value": 1}],
                )
            ]

        elif node_name == "verify_numbers_deterministically":
            updates["number_check_result"] = value

        elif node_name == "verify_claim_support_and_intent":
            updates["verification"] = VerificationResult(
                claims_supported=value == "supported",
                intent_aligned=value == "supported",
                score=1.0 if value == "supported" else 0.0,
            )

        elif node_name == "calibrate_end_to_end_confidence":
            updates["confidence"] = ConfidenceResult(
                probability=1.0,
                badge_level="not verified",
            )

        elif node_name == "validate_existing_result_for_chart":
            updates["chart_result"] = value

        elif node_name == "select_chart_type":
            updates["chart"] = ChartSpec(chart_type=str(value))

        elif node_name == "render_chart":
            updates["outcome"] = "charted"

        elif node_name == "describe_from_metadata":
            updates["outcome"] = "described"

        elif node_name == "search_catalog_entries":
            updates["outcome"] = "searched"

        elif node_name == "explain_from_evidence":
            updates["outcome"] = "explained"

        elif node_name == "ask_clarification":
            updates["outcome"] = "clarifying"

        elif node_name == "decline_and_log_data_request":
            updates["outcome"] = "declined"
            updates["outcome_cause"] = "not_covered"

        elif node_name == "abstain_with_reason":
            updates["outcome"] = "abstained"
            updates["outcome_cause"] = state.get(
                "requested_cause", "unverified"
            )

        elif node_name == "report_system_failure":
            updates["outcome"] = "failed"
            updates["outcome_cause"] = state.get(
                "requested_cause", "backend_error"
            )

        elif node_name == "respond_out_of_scope":
            updates["outcome"] = "out_of_scope"

        elif node_name == "assemble_answer_and_evidence_panel":
            updates["outcome"] = "answered"

        elif node_name == "finalize_response":
            pass

        return updates

    return node
