"""The graph with the model-backed nodes on scripted LLM replies (no network, no credit).

The tool nodes (place, period and unit resolution, SQL validation and execution, derivations and
checks) stay stubs, except `resolve_places_periods_units`, which a small stand-in replaces here
because the coverage check needs a plan that names a real table.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from analyst.agents.graph import invoke_graph
from analyst.agents.model_nodes import ModelNodeDependencies, make_model_nodes
from analyst.agents.state import AnalystState, RunConfig
from analyst.contracts import IndicatorRef, InterpretationPlan, PeriodWindow, UnresolvedSlot
from analyst.decisions.router import Backends, RouterConfig
from analyst.inference.scripted import ScriptedTransport, scripted_client

RAIN = "imd_subdivision_monthly_rainfall"
PUBLISHED = {
    RAIN: {
        "dataset_id": RAIN,
        "title": "IMD rainfall by sub-division",
        "domain": "rainfall",
        "publisher": "IMD",
        "source_table": "t",
        "licence": "OGDL",
        "retrieved": "2026-11-17",
        "dataset_version": "1.0.0+x",
        "raw_sha256": "0" * 64,
        "obs_table": f"obs_{RAIN}",
        "geo_levels": ["subdivision"],
        "coverage_start": "1901-01-01",
        "coverage_end": "2017-12-31",
        "period_types": ["calendar_year"],
        "indicator_units": {"rainfall_mm": "mm"},
        "categories": {},
        "caveats": [],
    }
}
ROUTE = {"tool": "run_sql", "domain": "rainfall"}
SQL = {
    "sql": f"SELECT period_label, value FROM obs_{RAIN} WHERE period_label = '2010'",
    "statement": "Annual rainfall in 2010",
}
NARRATION = {
    "text": "Kerala received 1.0 mm in 2010.",
    "claims": [
        {
            "text": "Kerala received 1.0 mm in 2010.",
            "numbers": [{"text": "1.0", "cell": {"row": 0, "column": "value"}, "derived_id": None}],
        }
    ],
}


def intent(period: str = "2010") -> dict[str, Any]:
    return {
        "action": "answer",
        "dataset_id": RAIN,
        "indicator_ids": ["rainfall_mm"],
        "place_mentions": ["Kerala"],
        "all_places_level": None,
        "period_mentions": [period],
        "categories": {},
        "operation": "lookup",
        "order": None,
        "limit": None,
        "derivations": [],
        "changed_slots": [],
        "reason": None,
    }


def resolver(state: AnalystState) -> dict[str, Any]:
    """Stand-in for the resolver: one table, one calendar year; 'monsoon' is unresolved.
    An intent with no fitting table gets the no-fit plan, as in the real resolver."""
    if state.intent is not None and state.intent.dataset_id == "none_fit":
        from analyst.agents.tool_nodes import _no_fit_plan

        return {"plan": _no_fit_plan(state.intent)}
    mention = state.intent.period_mentions[0] if state.intent else "2010"
    unresolved = (
        [UnresolvedSlot(slot="period", mention=mention, options=["JJAS", "OND"])]
        if mention == "monsoon"
        else []
    )
    year = int(mention) if mention.isdigit() else 2010
    plan = InterpretationPlan(
        dataset_id=RAIN,
        obs_table=f"obs_{RAIN}",
        dataset_version="1.0.0+x",
        indicators=[IndicatorRef(indicator_id="rainfall_mm", label="Rainfall", unit="mm")],
        places=[],
        all_places_level=None,
        periods=[
            PeriodWindow(
                requested=mention,
                type="calendar_year",
                label=str(year),
                start=date(year, 1, 1),
                end=date(year, 12, 31),
            )
        ],
        categories={},
        operation="lookup",
        order=None,
        limit=None,
        derivations=[],
        exclude_total_rows=True,
        assumptions=[],
        unresolved=unresolved,
    )
    update: dict[str, Any] = {"plan": plan}
    if state.plan is not None:
        update["counters"] = state.counters.bumped("resolution_retries")
    return update


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "configs").symlink_to(root / "configs")
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "catalogue.json").write_text(json.dumps({"tables": list(PUBLISHED.values())}))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(
    *replies: Any,
    question: str = "What was the annual rainfall in Kerala in 2010?",
    max_llm_calls: int = 8,
    **script: list[Any],
) -> tuple[AnalystState, ScriptedTransport]:
    client, transport = scripted_client(*replies, max_llm_calls=max_llm_calls)
    deps = ModelNodeDependencies(client, RouterConfig.from_files("v0"), Backends(llm=client))
    nodes = {**make_model_nodes(deps), "resolve_places_periods_units": resolver}
    config = RunConfig(version="v0", stub_script=script)
    state = AnalystState(run_id="r1", question=question, config=config)
    return invoke_graph(state, overrides=nodes), transport


def run_with(
    fields: dict[str, Any], *replies: Any, question: str, **script: list[Any]
) -> tuple[AnalystState, ScriptedTransport]:
    """`run` with extra initial state fields (for example a stored result reference)."""
    client, transport = scripted_client(*replies, max_llm_calls=8)
    deps = ModelNodeDependencies(client, RouterConfig.from_files("v0"), Backends(llm=client))
    nodes = {**make_model_nodes(deps), "resolve_places_periods_units": resolver}
    config = RunConfig(version="v0", stub_script=script)
    state = AnalystState(run_id="r1", question=question, config=config, **fields)
    return invoke_graph(state, overrides=nodes), transport


def test_answer(workdir: Path) -> None:
    state, transport = run(ROUTE, intent(), SQL, NARRATION)
    assert (state.outcome, state.outcome_cause) == ("answered", None)
    assert state.response_text == NARRATION["text"]
    assert [r.purpose for r in state.llm_records] == ["route", "intent", "sql", "narrate"]
    assert state.counters.llm_calls == len(transport.calls) == 4  # counted once, by the client
    assert state.counters.sql_generations == 1 and state.counters.narrations == 1
    assert state.routing is not None and state.routing.final_tool == "run_sql"
    assert state.sql[0].kind == "generate" and "obs_imd" in state.sql[0].sql
    assert state.evidence is not None and state.evidence.sources[0].dataset_id == RAIN
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        calls = db.execute("SELECT node, prompt_id FROM llm_calls ORDER BY seq").fetchall()
        runs = db.execute("SELECT llm_calls, outcome FROM runs").fetchone()
    assert [c[0] for c in calls] == [
        "route_tool_and_domain",
        "extract_query_intent",
        "generate_sql_with_hosted_llm",
        "narrate_from_result_only",
    ]
    assert runs == (4, "answered")


def test_a_period_gap_on_a_named_table_is_declined_without_widening(workdir: Path) -> None:
    # More tables cannot supply 2030, so no second intent call (dev run 3: wasted calls).
    state, _ = run(ROUTE, intent("2030"), question="Rainfall in Kerala in 2030?")
    assert (state.outcome, state.outcome_cause) == ("declined", "not_covered")
    assert state.counters.llm_calls == 2 and state.counters.widened_searches == 0
    assert state.coverage is not None and state.coverage.missing[0].kind == "period"
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        assert db.execute("SELECT count(*) FROM data_requests").fetchone()[0] == 1


def test_a_pointer_to_another_table_widens_the_search_once(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fixture catalogue has one table; the pointer check is tested in test_conversation.
    import analyst.inference.intent as intent_mod

    monkeypatch.setattr(intent_mod, "_checked_pointer", lambda parsed, _retrieved: parsed)
    pointed = {
        **intent("2030"),
        "action": "decline",
        "dataset_id": "none_fit",
        "indicator_ids": [],
        "reason": "Another catalogue table holds the measure.",
        "follow_up": False,
        "catalogue_dataset_id": "plfs_state_ur_usual_status",
    }
    state, _ = run(ROUTE, pointed, intent("2030"), question="Rainfall in Kerala in 2030?")
    assert state.counters.widened_searches == 1 and state.counters.llm_calls == 3
    assert state.outcome == "declined"


def test_clarification_text_is_written_by_the_llm(workdir: Path) -> None:
    reply = {"question": "Which monsoon season do you mean?"}
    state, _ = run(ROUTE, intent("monsoon"), reply, question="Rainfall in Kerala in the monsoon?")
    assert state.outcome == "clarifying"
    assert state.response_text.startswith("Which monsoon season do you mean?")
    assert state.pending_clarification is not None
    assert state.pending_clarification.options == ["JJAS", "OND"]
    assert [r.purpose for r in state.llm_records] == ["route", "intent", "clarify"]


def test_repair_is_called_for_an_invalid_query(workdir: Path) -> None:
    state, _ = run(
        ROUTE, intent(), SQL, SQL, NARRATION, validate_sql_with_sqlglot=["invalid", "valid"]
    )
    assert state.outcome == "answered"
    assert [a.kind for a in state.sql] == ["generate", "repair"]
    assert state.counters.sql_repairs == 1 and state.counters.llm_calls == 5
    assert [r.purpose for r in state.llm_records][2:4] == ["sql", "sql_repair"]


def test_backend_failure_ends_the_run_as_backend_error(workdir: Path) -> None:
    state, _ = run()  # the script is empty: the router's LLM call fails
    assert (state.outcome, state.outcome_cause) == ("failed", "backend_error")
    assert state.node_error == "backend_error"


def test_budget_of_the_client_ends_the_run_as_budget_exhausted(workdir: Path) -> None:
    state, _ = run(ROUTE, intent(), max_llm_calls=1)
    assert (state.outcome, state.outcome_cause) == ("failed", "budget_exhausted")


def test_graph_budget_limit_stops_before_the_next_llm_node(workdir: Path) -> None:
    client, _ = scripted_client(ROUTE, intent(), SQL, NARRATION)
    deps = ModelNodeDependencies(client, RouterConfig.from_files("v0"), Backends(llm=client))
    nodes = {**make_model_nodes(deps), "resolve_places_periods_units": resolver}
    config = RunConfig(version="v0")
    config.limits.max_llm_calls = 2
    state = invoke_graph(AnalystState(run_id="r1", question="q", config=config), overrides=nodes)
    assert (state.outcome, state.outcome_cause) == ("failed", "budget_exhausted")
    assert state.counters.llm_calls == 2


DECLINE_ROUTE = {"tool": "decline_not_covered", "domain": "other"}
# The decline shortcut is off until its thresholds are set, so the intent declines first.
NO_FIT = {
    **intent(),
    "action": "decline",
    "dataset_id": "none_fit",
    "indicator_ids": [],
    "place_mentions": [],
    "period_mentions": [],
    "reason": "No listed dataset holds this.",
}


def test_distress_gets_a_kind_reply_and_the_helpline_and_no_data_request(workdir: Path) -> None:
    reply = {"kind": "personal_distress", "reply": "I am sorry you are feeling this way."}
    state, _ = run(DECLINE_ROUTE, NO_FIT, reply, question="I am feeling sad, what can I do now?")
    assert state.outcome == "out_of_scope"
    assert state.response_text.startswith("I am sorry you are feeling this way.")
    assert "Tele-MANAS" in state.response_text and "14416" in state.response_text
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        assert db.execute("SELECT count(*) FROM data_requests").fetchone()[0] == 0


def test_a_non_data_request_is_out_of_scope(workdir: Path) -> None:
    reply = {
        "kind": "not_data",
        "reply": "I answer questions on Indian public data, such as prices or rainfall.",
    }
    state, _ = run(DECLINE_ROUTE, NO_FIT, reply, question="Help me write a python code")
    assert state.outcome == "out_of_scope" and "public data" in state.response_text
    assert [r.purpose for r in state.llm_records] == ["route", "intent", "decline"]


def test_a_data_request_not_covered_is_logged(workdir: Path) -> None:
    reply = {
        "kind": "not_covered",
        "reply": "Today's weather is not in the catalogue, which holds official statistics; "
        "the request has been noted.",
    }
    state, _ = run(DECLINE_ROUTE, NO_FIT, reply, question="What is the weather today?")
    assert state.outcome == "declined"
    assert state.response_text.startswith("Today's weather is not in the catalogue")
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        assert db.execute("SELECT count(*) FROM data_requests").fetchone()[0] == 1


def test_a_decline_reply_with_an_invented_number_falls_back_to_the_template(
    workdir: Path,
) -> None:
    bad = {"kind": "not_covered", "reply": "It will be 31 degrees today."}
    state, _ = run(DECLINE_ROUTE, NO_FIT, bad, bad, question="What is the weather today?")
    assert state.outcome == "declined"
    assert state.response_text.startswith("The catalogue does not contain the requested data.")


def test_a_definition_is_answered_from_the_documentation(workdir: Path) -> None:
    route = {"tool": "describe_table", "domain": "rainfall"}
    reply = {"documented": False, "answer": "The catalogue does not document JJAS."}
    state, _ = run(route, reply, question="What is JJAS?")
    assert state.outcome == "described"
    assert state.response_text == "The catalogue does not document JJAS."
    assert [r.purpose for r in state.llm_records] == ["route", "describe"]


def test_a_describe_request_that_asks_for_figures_continues_as_a_query(workdir: Path) -> None:
    # UI test, 19 Nov: "Could you comment about all the categories?" after an answer.
    route = {"tool": "describe_table", "domain": "rainfall"}
    handover = {"data_request": True, "documented": False, "answer": ""}
    state, _ = run(
        route,
        handover,
        intent(),
        SQL,
        NARRATION,
        question="Comment on the annual rainfall in Kerala",
    )
    assert state.outcome == "answered"
    purposes = [r.purpose for r in state.llm_records]
    assert purposes[:3] == ["route", "describe", "intent"] and "narrate" in purposes


def test_an_explain_request_that_asks_for_figures_continues_as_a_query(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Smoke run, 19 Nov: "How much did it change between those two years?" was explained.
    from types import SimpleNamespace

    import analyst.tools.evidence as evidence_mod

    bundle = SimpleNamespace(
        statement="s",
        sql="SELECT 1",
        result=SimpleNamespace(columns=[], rows=[]),
        sources=[],
        assumptions=[],
        caveats=[],
        evidence_id="ev1",
    )
    monkeypatch.setattr(evidence_mod.EvidenceStore, "get", lambda self, ref: bundle)
    route = {"tool": "explain_result", "domain": "rainfall"}
    handover = {"data_request": True, "documented": False, "answer": ""}
    config_state = {"prior_result_ref": "ev1"}
    state, _ = run_with(
        config_state,
        route,
        handover,
        intent(),
        SQL,
        NARRATION,
        question="Compare the annual rainfall in Kerala",
    )
    assert state.outcome == "answered"
    assert [r.purpose for r in state.llm_records][:3] == ["route", "describe", "intent"]
