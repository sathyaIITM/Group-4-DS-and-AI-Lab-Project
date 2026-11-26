"""Milestone 5 fixes C1-C4 and B1-B3: clarification, abstention and periods (rule sheet v2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analyst.agents import control_nodes
from analyst.agents.state import AnalystState
from analyst.agents.stubs import stub_plan, stub_routing
from analyst.agents.tool_nodes import (
    ToolNodeDependencies,
    _missing_place,
    _needs_one_place,
    _order_slots,
    check_missing_values_kept,
    make_tool_nodes,
    review_intent,
)
from analyst.contracts import QueryIntent, UnresolvedSlot
from analyst.contracts.common import IndicatorRef
from analyst.inference.clarify import check_question, fixed_question, names_detail, slot_detail
from analyst.tools.periods import asks_for_now, is_now_mention
from analyst.tools.resolve import resolve_plan
from analyst.tools.sql_runner import ReadOnlyDatabase

MANDI = {
    "dataset_id": "mandi",
    "dataset_version": "v1",
    "obs_table": "obs_mandi",
    "geo_levels": ["market"],
    "period_types": ["date"],
    "categories": {"commodity_name": 261, "variety": 548},
    "indicator_units": {"modal_price": "INR_per_quintal"},
    "coverage_start": "2026-10-29",
    "coverage_end": "2026-10-29",
}
RAIN = {
    "dataset_id": "rain",
    "dataset_version": "v1",
    "obs_table": "obs_rain",
    "domain": "rainfall",
    "geo_levels": ["subdivision"],
    "period_types": ["calendar_year"],
    "indicator_units": {"rainfall_mm": "mm"},
}
PLFS = {
    "dataset_id": "plfs",
    "dataset_version": "v1",
    "obs_table": "obs_plfs",
    "domain": "labour",
    "geo_levels": ["national", "state"],
    "period_types": ["survey_year"],
    "period_start_month": 7,
    "indicator_units": {"ur": "percent"},
}
CATALOGUE = {"mandi": MANDI, "rain": RAIN, "plfs": PLFS}


def _intent(**changes: Any) -> QueryIntent:
    fields: dict[str, Any] = {
        "action": "answer",
        "dataset_id": "mandi",
        "indicator_ids": [],
        "place_mentions": [],
        "all_places_level": None,
        "period_mentions": [],
        "categories": {},
        "operation": "lookup",
        "order": None,
        "limit": None,
        "derivations": [],
        "changed_slots": [],
        "reason": None,
    }
    fields.update(changes)
    return QueryIntent.model_validate(fields)


def _mandi_db(tmp_path: Path) -> ReadOnlyDatabase:
    parquet = tmp_path / "obs_mandi.parquet"
    pd.DataFrame(
        {
            "dataset_version": ["v1"] * 2,
            "geo_level": ["market"] * 2,
            "geo_code": ["market:azadpur", "market:lasalgaon"],
            "geo_name": ["Azadpur", "Lasalgaon"],
            "geo_state": ["Delhi", "Maharashtra"],
            "geo_district": ["North West Delhi", "Nashik"],
            "geo_vintage": ["2011"] * 2,
            "indicator_id": ["modal_price"] * 2,
            "indicator_label_source": ["Modal price"] * 2,
            "commodity_name": ["Onion", "Potato"],
            "period_type": ["date"] * 2,
            "period_label": ["2026-10-29"] * 2,
            "period_start": pd.to_datetime(["2026-10-29"] * 2),
            "period_end": pd.to_datetime(["2026-10-29"] * 2),
        }
    ).to_parquet(parquet)
    return ReadOnlyDatabase({"obs_mandi": parquet})


def _plfs_db(tmp_path: Path) -> ReadOnlyDatabase:
    parquet = tmp_path / "obs_plfs.parquet"
    pd.DataFrame(
        {
            "dataset_version": ["v1"] * 2,
            "geo_level": ["state"] * 2,
            "geo_code": ["state:kerala"] * 2,
            "geo_name": ["Kerala"] * 2,
            "geo_vintage": ["2011"] * 2,
            "indicator_id": ["ur"] * 2,
            "indicator_label_source": ["Unemployment rate"] * 2,
            "period_type": ["survey_year"] * 2,
            "period_label": ["2020-21", "2021-22"],
            "period_start": pd.to_datetime(["2020-07-01", "2021-07-01"]),
            "period_end": pd.to_datetime(["2021-06-30", "2022-06-30"]),
        }
    ).to_parquet(parquet)
    return ReadOnlyDatabase({"obs_plfs": parquet})


# C1: the missing slot is named, in the order of rule S1.


def test_slot_detail_names_the_column_or_the_place_level() -> None:
    assert slot_detail("category", "commodity_name was not named", MANDI) == "commodity"
    assert slot_detail("category", "variety was not named", MANDI) == "variety"
    assert slot_detail("category", "The table covers persons aged 15+ only.", PLFS) == "group"
    assert slot_detail("place", "no place was named", MANDI) == "market"
    assert slot_detail("place", "no place was named", RAIN) == "sub-division"
    assert slot_detail("place", "Aurangabad", PLFS) == "place"  # two levels: neutral word
    assert slot_detail("period", "during demonetisation", PLFS) == "period"
    assert slot_detail("indicator", "", None) == "measure"


def test_fixed_question_always_names_the_detail() -> None:
    assert fixed_question("commodity", "category", "commodity_name was not named") == (
        "Which commodity do you mean?"
    )
    assert fixed_question("market", "place", "no place was named") == "Which market do you mean?"
    assert fixed_question("period", "period", "the lockdown") == (
        "Which period is meant by 'the lockdown'?"
    )


def test_a_generic_clarification_is_rejected() -> None:
    with pytest.raises(ValueError, match="commodity"):
        check_question("Which category do you mean?", "Mandi price in Azadpur?", [], "commodity")
    check_question("Which commodity do you mean?", "Mandi price in Azadpur?", [], "commodity")
    assert names_detail("Which monsoon season do you mean?", "period")
    assert names_detail("Which subdivision?", "sub-division")
    assert not names_detail("Could you specify the category?", "group")


def test_ask_clarification_names_the_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control_nodes, "published_catalogue", lambda: CATALOGUE)
    slot = UnresolvedSlot(slot="category", mention="commodity_name was not named", options=[])
    plan = stub_plan("mandi").model_copy(update={"unresolved": [slot]})
    update = control_nodes.ask_clarification(AnalystState(plan=plan))
    assert update["response_text"] == "Which commodity do you mean?"


def test_a_price_with_no_commodity_and_no_market_asks_the_commodity(tmp_path: Path) -> None:
    nodes = make_tool_nodes(ToolNodeDependencies(CATALOGUE, {}, lambda _d: _mandi_db(tmp_path)))
    intent = _intent(indicator_ids=["modal_price"])
    plan = nodes["resolve_places_periods_units"](AnalystState(intent=intent))["plan"]
    assert [u.slot for u in plan.unresolved] == ["category"]
    assert plan.unresolved[0].mention == "commodity_name was not named"
    # With the commodity named, the missing market is asked (no national row).
    named = intent.model_copy(update={"categories": {"commodity_name": ["Onion"]}})
    plan = nodes["resolve_places_periods_units"](AnalystState(intent=named))["plan"]
    assert [u.slot for u in plan.unresolved] == ["place"]
    # A ranking across commodities needs no commodity.
    ranking = intent.model_copy(update={"operation": "ranking", "place_mentions": ["Azadpur"]})
    plan = nodes["resolve_places_periods_units"](AnalystState(intent=ranking))["plan"]
    assert not [u for u in plan.unresolved if u.slot == "category"]


def test_the_intents_commodity_question_comes_before_an_unmatched_market(tmp_path: Path) -> None:
    nodes = make_tool_nodes(ToolNodeDependencies(CATALOGUE, {}, lambda _d: _mandi_db(tmp_path)))
    intent = _intent(
        action="clarify",
        missing_slot="category",
        place_mentions=["Nowhere Mandi"],
        reason="No commodity named.",
    )
    plan = nodes["resolve_places_periods_units"](AnalystState(intent=intent))["plan"]
    assert [u.slot for u in plan.unresolved][:2] == ["category", "place"]


def test_unresolved_slots_follow_rule_s1() -> None:
    slots = [
        UnresolvedSlot(slot="period", mention="x", options=[]),
        UnresolvedSlot(slot="place", mention="y", options=[]),
        UnresolvedSlot(slot="indicator", mention="z", options=[]),
    ]
    plan = _order_slots(stub_plan("demo").model_copy(update={"unresolved": slots}))
    assert [u.slot for u in plan.unresolved] == ["indicator", "place", "period"]


# C2: a group the table lacks is asked, not declined; a missing measure stays a decline.


def test_a_decline_for_a_missing_group_becomes_a_clarification() -> None:
    declined = _intent(action="decline", dataset_id="plfs", missing_slot="category", reason="r")
    assert review_intent(declined, PLFS, "Youth unemployment in Bihar?").action == "clarify"
    measure = declined.model_copy(update={"missing_slot": "indicator"})
    assert review_intent(measure, PLFS, "How many people are unemployed?").action == "decline"
    assert review_intent(declined, None, "q").action == "decline"  # no listed table


# B1: "now", "currently", "latest" take the latest published period.


def test_now_words_are_recognised() -> None:
    assert is_now_mention("right now") and is_now_mention("Latest") and is_now_mention("today")
    assert not is_now_mention("2019-20") and not is_now_mention("last month")
    assert asks_for_now("What is the unemployment rate in Kerala right now?")
    assert not asks_for_now("Unemployment in Kerala in 2019-20?")


def test_a_period_decline_for_now_becomes_an_answer_except_for_weather() -> None:
    declined = _intent(
        action="decline",
        dataset_id="plfs",
        missing_slot="period",
        period_mentions=["right now"],
        reason="The table ends in 2021-22.",
    )
    answered = review_intent(declined, PLFS, "Unemployment in Kerala right now?")
    assert answered.action == "answer" and answered.missing_slot is None
    assert answered.period_mentions == ["right now"]
    bare = declined.model_copy(update={"period_mentions": []})
    assert review_intent(bare, PLFS, "Kerala jobless rate currently?").period_mentions == [
        "currently"
    ]
    weather = declined.model_copy(update={"dataset_id": "rain"})
    assert review_intent(weather, RAIN, "Is it raining in Kerala right now?").action == "decline"
    last_month = declined.model_copy(update={"period_mentions": ["last month"]})
    assert review_intent(last_month, PLFS, "Unemployment last month?").action == "decline"


def test_a_now_mention_resolves_to_the_latest_period_and_says_so(tmp_path: Path) -> None:
    intent = _intent(
        dataset_id="plfs",
        indicator_ids=["ur"],
        place_mentions=["Kerala"],
        period_mentions=["right now"],
        operation="trend",  # D1 applies to "now" whatever the operation
    )
    plan = resolve_plan(
        intent,
        dataset=PLFS,
        indicators=[{"indicator_id": "ur", "label": "Unemployment rate", "unit": "percent"}],
        db=_plfs_db(tmp_path),
        refs={},
        catalogue=CATALOGUE,
    )
    assert not plan.unresolved and [p.label for p in plan.periods] == ["2021-22"]
    assert plan.assumptions[0].code == "D1" and "'right now'" in plan.assumptions[0].text


def test_the_resolve_node_answers_a_now_decline_with_the_latest_period(tmp_path: Path) -> None:
    nodes = make_tool_nodes(ToolNodeDependencies(CATALOGUE, {}, lambda _d: _plfs_db(tmp_path)))
    intent = _intent(
        action="decline",
        dataset_id="plfs",
        indicator_ids=["ur"],
        place_mentions=["Kerala"],
        missing_slot="period",
        reason="The table ends in 2021-22.",
    )
    state = AnalystState(question="What is Kerala's unemployment rate right now?", intent=intent)
    update = nodes["resolve_places_periods_units"](state)
    assert update["intent"].action == "answer"
    assert update["plan"].dataset_id == "plfs"
    assert [p.label for p in update["plan"].periods] == ["2021-22"]


# C3: a place-level measure with no place is asked for the place.


def test_an_aggregate_of_a_non_additive_measure_needs_a_place() -> None:
    mm = IndicatorRef(indicator_id="rainfall_mm", label="Rainfall", unit="mm")
    plan = stub_plan("rain").model_copy(
        update={"operation": "aggregate", "indicators": [mm], "places": [], "unresolved": []}
    )
    assert _needs_one_place(plan, RAIN)
    asked = _missing_place(plan, _intent(dataset_id="rain"), RAIN)
    assert [u.slot for u in asked.unresolved] == ["place"]
    tonnes = {"indicator_units": {"rainfall_mm": "tonne"}}
    assert not _needs_one_place(plan, tonnes)  # a production total adds up over districts
    ranking = plan.model_copy(update={"operation": "ranking"})
    assert not _needs_one_place(ranking, RAIN)


# C4: a question about a table is described, not answered with a catalogue search.


@pytest.mark.parametrize(
    ("question", "branch"),
    [
        ("What does the PLFS unemployment table cover?", "describe"),
        ("In what unit are the mandi prices reported?", "describe"),
        ("What does JJAS mean in the rainfall data?", "describe"),
        ("Is there data on crime in India?", "search"),
        ("Which datasets cover health?", "search"),
    ],
)
def test_a_describe_question_routed_to_search_is_described(question: str, branch: str) -> None:
    state = AnalystState(question=question, routing=stub_routing("search_catalog", "other"))
    routing = control_nodes.resolve_routing_decision(state)["routing"]
    assert routing.branch == branch
    assert routing.tool.label == "search_catalog"  # the decision model's own choice is kept


# B3: rows the publisher suppressed are reported, not dropped.


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM obs_demo WHERE value IS NOT NULL AND quality_flag <> 'implausible'",
        "SELECT * FROM obs_demo WHERE quality_flag = 'ok'",
        "SELECT * FROM obs_demo WHERE quality_flag NOT IN ('implausible', 'suppressed')",
    ],
)
def test_a_query_that_drops_missing_values_is_repaired(sql: str) -> None:
    with pytest.raises(ValueError, match="quality_flag"):
        check_missing_values_kept(sql, stub_plan("demo"))


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM obs_demo WHERE quality_flag <> 'implausible'",
        "SELECT * FROM obs_demo WHERE quality_flag NOT IN ('implausible')",
        "SELECT * FROM obs_demo WHERE COALESCE(quality_flag, 'ok') <> 'implausible'",
        "SELECT * FROM obs_demo WHERE value IS NOT NULL ORDER BY value DESC LIMIT 5",
    ],
)
def test_queries_that_keep_missing_values_pass(sql: str) -> None:
    check_missing_values_kept(sql, stub_plan("demo"))
    ranking = stub_plan("demo").model_copy(update={"operation": "ranking"})
    check_missing_values_kept(
        "SELECT * FROM obs_demo WHERE value IS NOT NULL AND quality_flag <> 'implausible'", ranking
    )
