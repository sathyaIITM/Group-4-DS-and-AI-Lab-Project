"""The graph with T3's nodes on scripted LLM replies (no network, no credit).

T4's nodes (place, period and unit resolution, SQL validation and execution, derivations and
checks) stay stubs, except `resolve_places_periods_units`, which a small stand-in replaces here
because T3's coverage check needs a plan that names a real table.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from analyst.agents.graph import invoke_graph
from analyst.agents.state import AnalystState, RunConfig
from analyst.agents.t3_nodes import T3Dependencies, make_t3_nodes
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
    """Stand-in for T4's resolve_plan: one table, one calendar year; 'monsoon' is unresolved."""
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
    deps = T3Dependencies(client, RouterConfig.from_files("v0"), Backends(llm=client))
    nodes = {**make_t3_nodes(deps), "resolve_places_periods_units": resolver}
    config = RunConfig(version="v0", stub_script=script)
    state = AnalystState(run_id="r1", question=question, config=config)
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


def test_decline_after_one_widened_search(workdir: Path) -> None:
    state, _ = run(ROUTE, intent("2030"), intent("2030"), question="Rainfall in Kerala in 2030?")
    assert (state.outcome, state.outcome_cause) == ("declined", "not_covered")
    assert state.counters.llm_calls == 3 and state.counters.widened_searches == 1
    assert state.coverage is not None and state.coverage.missing[0].kind == "period"
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        assert db.execute("SELECT count(*) FROM data_requests").fetchone()[0] == 1


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
    deps = T3Dependencies(client, RouterConfig.from_files("v0"), Backends(llm=client))
    nodes = {**make_t3_nodes(deps), "resolve_places_periods_units": resolver}
    config = RunConfig(version="v0")
    config.limits.max_llm_calls = 2
    state = invoke_graph(AnalystState(run_id="r1", question="q", config=config), overrides=nodes)
    assert (state.outcome, state.outcome_cause) == ("failed", "budget_exhausted")
    assert state.counters.llm_calls == 2
