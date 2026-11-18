"""Regression tests for the review of the T4 tool and evaluation branches (18 November)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from analyst.agents.state import AnalystState
from analyst.agents.stubs import stub_plan
from analyst.agents.tool_nodes import ToolNodeDependencies, make_tool_nodes
from analyst.contracts import DerivationRequest, PeriodWindow, Place, QueryIntent
from analyst.contracts.results import QueryResult
from analyst.evaluation.e2e_eval import _case_success, _narrated_numbers, score_cases
from analyst.tools.checks import run_intent_checks
from analyst.tools.numbers import verify_numbers
from analyst.tools.periods import resolve_period
from analyst.tools.sql_runner import ReadOnlyDatabase

CATALOGUE = {
    "demo": {
        "dataset_id": "demo",
        "dataset_version": "v1",
        "obs_table": "obs_demo",
        "geo_levels": ["state"],
        "period_types": ["survey_year"],
        "period_start_month": 7,
        "indicator_units": {"ur": "percent"},
    },
    "nfhs": {
        "dataset_id": "nfhs",
        "period_types": ["survey_round"],
        "period_start_month": None,
        "coverage_start": "2019-01-01",
        "coverage_end": "2021-12-31",
    },
    "gsdp": {"dataset_id": "gsdp", "period_types": ["survey_year"], "period_start_month": 4},
}


def _window(label: str, year: int) -> PeriodWindow:
    return PeriodWindow(
        requested=label,
        type="survey_year",
        label=label,
        start=date(year, 7, 1),
        end=date(year + 1, 6, 30),
    )


def _place(name: str) -> Place:
    return Place(
        requested=name, level="state", code=f"state:{name.lower()}", name=name, match="exact"
    )


def _result(rows: list[list[object]]) -> QueryResult:
    columns = [{"name": n, "type": "VARCHAR"} for n in ("geo_name", "period_label")]
    return QueryResult.model_validate(
        {
            "sql": "SELECT 1",
            "columns": [*columns, {"name": "value", "type": "DOUBLE"}],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
            "dataset_versions": {"demo": "v1"},
            "exec_ms": 1,
        }
    )


def test_resolve_node_reads_places_through_the_read_only_database(tmp_path: Path) -> None:
    parquet = tmp_path / "obs_demo.parquet"
    pd.DataFrame(
        {
            "dataset_version": ["v1"],
            "geo_code": ["state:kerala"],
            "geo_name": ["Kerala"],
            "geo_level": ["state"],
            "geo_vintage": ["2011"],
            "indicator_id": ["ur"],
            "indicator_label_source": ["Unemployment rate"],
        }
    ).to_parquet(parquet)
    nodes = make_tool_nodes(
        ToolNodeDependencies(
            catalogue=CATALOGUE,
            refs={},
            database_for=lambda _d: ReadOnlyDatabase({"obs_demo": parquet}),
        )
    )
    intent = QueryIntent(
        action="answer",
        dataset_id="demo",
        indicator_ids=[],
        place_mentions=["Kerala"],
        all_places_level=None,
        period_mentions=["2019"],
        categories={},
        operation="lookup",
        order=None,
        limit=None,
        derivations=[],
        changed_slots=[],
        reason=None,
    )
    update = nodes["resolve_places_periods_units"](AnalystState(intent=intent))
    plan = update["plan"]
    assert [place.name for place in plan.places] == ["Kerala"]
    assert plan.periods[0].label == "2019-20"
    assert [item.code for item in plan.assumptions] == ["D7"]


def test_resolve_node_reports_a_fault_instead_of_raising() -> None:
    def broken(_dataset: str) -> ReadOnlyDatabase:
        raise FileNotFoundError("obs_demo.parquet")

    nodes = make_tool_nodes(ToolNodeDependencies(CATALOGUE, {}, broken))
    intent = QueryIntent.model_validate(
        {
            "action": "answer",
            "dataset_id": "demo",
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
    )
    update = nodes["resolve_places_periods_units"](AnalystState(intent=intent))
    assert update["node_error"] == "backend_error"


def _derive(
    derivations: list[DerivationRequest], rows: list[list[object]], places: list[str]
) -> list:
    plan = stub_plan("demo").model_copy(
        update={
            "periods": [_window("2017-18", 2017), _window("2021-22", 2021)],
            "places": [_place(p) for p in places],
            "derivations": derivations,
        }
    )
    nodes = make_tool_nodes(ToolNodeDependencies(CATALOGUE, {}, lambda _d: None))  # type: ignore[arg-type,return-value]
    state = AnalystState(plan=plan, result=_result(rows))
    return nodes["compute_derivations"](state)["derived"]


def test_derivations_use_the_intent_period_arguments_per_place() -> None:
    request = DerivationRequest(
        op="pct_change", args={"from_period": "2017-18", "to_period": "2021-22"}
    )
    derived = _derive(
        [request],
        [
            ["Kerala", "2017-18", 10.0],
            ["Kerala", "2021-22", 8.0],
            ["Bihar", "2017-18", 5.0],
            ["Bihar", "2021-22", 6.0],
        ],
        ["Kerala", "Bihar"],
    )
    assert [(d.note, d.status, d.output) for d in derived] == [
        ("Kerala", "ok", Decimal("-20.0")),
        ("Bihar", "ok", Decimal("20.0")),
    ]
    assert [d.id for d in derived] == ["d1", "d2"]
    assert derived[0].inputs[0].row == 0


def test_cagr_and_change_pp_run_on_float_cells() -> None:
    rows: list[list[object]] = [["Kerala", "2017-18", 100.0], ["Kerala", "2021-22", 121.0]]
    args = {"from_period": "2017-18", "to_period": "2021-22"}
    cagr, change = _derive(
        [DerivationRequest(op="cagr", args=args), DerivationRequest(op="change_pp", args=args)],
        rows,
        ["Kerala"],
    )
    assert cagr.status == "ok" and abs(float(cagr.output) - 4.8809) < 1e-3  # 4 years
    assert change.output == Decimal("21.0") and change.unit == "percentage points"


def test_missing_input_is_reported_not_raised() -> None:
    request = DerivationRequest(
        op="pct_change", args={"from_period": "2017-18", "to_period": "2021-22"}
    )
    (derived,) = _derive([request], [["Kerala", "2017-18", 10.0]], ["Kerala"])
    assert derived.status == "input_unreported" and derived.output is None


def test_survey_round_matches_the_published_label() -> None:
    resolution = resolve_period("2019-21", "nfhs", CATALOGUE, ["2019-2021"])
    assert resolution.status == "resolved"
    assert resolution.window is not None and resolution.window.label == "2019-2021"
    assert resolution.window.start == date(2019, 1, 1)
    assert resolve_period("2015-16", "nfhs", CATALOGUE, ["2019-2021"]).status == "unresolved"


def test_april_start_year_uses_the_catalogue_start_month() -> None:
    window = resolve_period("2020-21", "gsdp", CATALOGUE).window
    assert window is not None and window.start == date(2020, 4, 1)
    assert window.end == date(2021, 3, 31)


def test_aggregate_result_without_place_column_is_not_a_query_fault() -> None:
    plan = stub_plan("demo").model_copy(update={"places": [_place("Kerala")]})
    result = QueryResult.model_validate(
        {
            "sql": "SELECT avg(value) AS value FROM obs_demo",
            "columns": [{"name": "value", "type": "DOUBLE"}],
            "rows": [[7.5]],
            "row_count": 1,
            "truncated": False,
            "dataset_versions": {},
            "exec_ms": 1,
        }
    )
    places = next(o for o in run_intent_checks(plan, result) if o.name == "requested_places")
    assert places.passed


def test_number_check_accepts_the_number_as_written_or_in_base_units() -> None:
    assert verify_numbers("Output was 1,234 thousand tonnes.", [1234.0]).passed
    assert verify_numbers("About 12 lakh people.", [1_200_000]).passed
    assert not verify_numbers("About 13 lakh people.", [1_200_000, 12]).passed
    assert 12.0 in _narrated_numbers("12 lakh") and 1_200_000.0 in _narrated_numbers("12 lakh")


def test_router_clarification_scores_and_counts_as_a_non_answer() -> None:
    case = {
        "id": "c1",
        "expected_action": "clarify",
        "outcome": "clarifying",
        "unresolved_slots": [],
        "notes": "Missing slot: place.",
        "expected_values": [],
        "expected_entities": [],
    }
    assert _case_success(case)
    assert not _case_success({**case, "unresolved_slots": ["period"]})
    score = score_cases([case])
    assert score["abstention_precision"] == 1.0
    assert score["review_cases"][0]["slot_check"] == "manual"


# Second batch: findings of the offline integration run on e2e_dev (scripted LLM replies).

RAIN_CATALOGUE = {
    "rain": {"dataset_id": "rain", "period_types": ["calendar_year", "month", "season"]},
    "cpi": {"dataset_id": "cpi", "period_types": ["month"]},
}


def test_monsoon_mentions_use_the_published_season_label() -> None:
    for mention in ("monsoon 2015", "2015 monsoon", "2015 monsoon season", "JJAS 2015"):
        window = resolve_period(mention, "rain", RAIN_CATALOGUE).window
        assert window is not None and window.label == "2015-JJAS", mention


def test_a_year_on_a_monthly_table_is_the_span_of_its_months() -> None:
    resolution = resolve_period("2023", "cpi", RAIN_CATALOGUE)
    assert resolution.window is not None and resolution.window.type == "month"
    assert (resolution.window.start, resolution.window.end) == (
        date(2023, 1, 1),
        date(2023, 12, 31),
    )
    assert resolution.assumption is not None and resolution.assumption.code == "YEAR_SPAN"


def _market_db(tmp_path: Path) -> ReadOnlyDatabase:
    parquet = tmp_path / "obs_mandi.parquet"
    pd.DataFrame(
        {
            "dataset_version": ["v1"] * 3,
            "geo_level": ["market"] * 3,
            "geo_code": ["market:a", "market:b", "market:c"],
            "geo_name": ["Agra APMC", "Aurangabad", "Aurangabad"],
            "geo_state": ["Uttar Pradesh", "Bihar", "Maharashtra"],
            "geo_district": ["Agra", "Aurangabad", "Aurangabad"],
            "geo_vintage": ["2011"] * 3,
        }
    ).to_parquet(parquet)
    return ReadOnlyDatabase({"obs_mandi": parquet})


def test_a_state_on_a_market_table_resolves_as_a_filter(tmp_path: Path) -> None:
    from analyst.tools.resolve import resolve_plan

    intent = QueryIntent.model_validate(
        {
            "action": "answer",
            "dataset_id": "mandi",
            "indicator_ids": [],
            "place_mentions": ["Uttar Pradesh", "Aurangabad"],
            "all_places_level": None,
            "period_mentions": [],
            "categories": {},
            "operation": "comparison",
            "order": None,
            "limit": None,
            "derivations": [],
            "changed_slots": [],
            "reason": None,
        }
    )
    dataset = {"dataset_id": "mandi", "dataset_version": "v1", "geo_levels": ["market"]}
    plan = resolve_plan(
        intent, dataset=dataset, indicators=[], db=_market_db(tmp_path), refs={}, catalogue={}
    )
    assert [(p.level, p.code) for p in plan.places] == [("state", "state:uttar_pradesh")]
    assert [(u.slot, u.mention, len(u.options)) for u in plan.unresolved] == [
        ("place", "Aurangabad", 2)
    ]


def test_a_state_resolves_as_a_filter_when_the_question_names_markets(tmp_path: Path) -> None:
    # Dev run 3, e2e-042: "Uttar Pradesh versus West Bengal markets" set all_places_level to
    # market, which skipped the State filter and asked for a place.
    from analyst.tools.resolve import resolve_plan

    intent = QueryIntent.model_validate(
        {
            "action": "answer",
            "dataset_id": "mandi",
            "indicator_ids": [],
            "place_mentions": ["Uttar Pradesh"],
            "all_places_level": "market",
            "period_mentions": [],
            "categories": {},
            "operation": "ranking",
            "order": "desc",
            "limit": 1,
            "derivations": [],
            "changed_slots": [],
            "reason": None,
        }
    )
    dataset = {"dataset_id": "mandi", "dataset_version": "v1", "geo_levels": ["market"]}
    plan = resolve_plan(
        intent, dataset=dataset, indicators=[], db=_market_db(tmp_path), refs={}, catalogue={}
    )
    assert [(p.level, p.code) for p in plan.places] == [("state", "state:uttar_pradesh")]
    assert plan.all_places_level == "market"
    assert plan.unresolved == []


def test_a_clarification_with_one_fitting_measure_answers_with_it() -> None:
    # Dev run 3, e2e-047: "Options: Crime rate, total" was asked although the plan held it.
    from analyst.agents.tool_nodes import _single_measure
    from analyst.contracts.plan import IndicatorRef

    ref = IndicatorRef(indicator_id="total_crime_rate", label="Crime rate, total", unit="per lakh")
    plan = stub_plan("ncrb").model_copy(update={"indicators": [ref]})
    assert _single_measure("indicator", ["Crime rate, total"], plan)
    assert not _single_measure("indicator", ["Crime rate, total", "IPC"], plan)
    assert not _single_measure("period", ["2023"], plan)
    assert not _single_measure("indicator", ["Other"], plan)


def test_coverage_accepts_a_state_filter_on_a_market_table() -> None:
    from analyst.decisions.coverage import check_coverage

    plan = stub_plan("mandi").model_copy(
        update={"places": [_place("Kerala")], "periods": [], "indicators": []}
    )
    table = {
        "dataset_id": "mandi",
        "geo_levels": ["market"],
        "coverage_start": "2024-01-01",
        "coverage_end": "2024-12-31",
        "period_types": ["date"],
        "indicator_units": {},
    }
    assert check_coverage(plan, {"mandi": table}).status == "covered"


def _intent(action: str, dataset_id: str) -> QueryIntent:
    return QueryIntent.model_validate(
        {
            "action": action,
            "dataset_id": dataset_id,
            "indicator_ids": [],
            "place_mentions": ["Kerala"],
            "all_places_level": None,
            "period_mentions": [],
            "categories": {},
            "operation": "lookup",
            "order": None,
            "limit": None,
            "derivations": [],
            "changed_slots": [],
            "reason": "reason",
        }
    )


def test_decline_intents_reach_coverage_as_none_fit(tmp_path: Path) -> None:
    nodes = make_tool_nodes(
        ToolNodeDependencies(CATALOGUE, {}, lambda _d: _market_db(tmp_path))  # type: ignore[arg-type]
    )
    declined = nodes["resolve_places_periods_units"](
        AnalystState(intent=_intent("decline", "demo"))
    )
    assert declined["plan"].dataset_id == "none_fit"
    no_fit = nodes["resolve_places_periods_units"](AnalystState(intent=_intent("decline", "x")))
    assert no_fit["plan"].dataset_id == "none_fit" and "node_error" not in no_fit


def test_derivation_statuses_follow_the_design_classes() -> None:
    from analyst.tools.checks import NOT_IN_RESULT, run_result_checks

    plan = stub_plan("demo").model_copy(update={"periods": [], "indicators": []})
    result = _result([["Kerala", "2017-18", 10.0]])

    def verdict(status: str, note: str) -> str:
        derived = [{"op": "pct_change", "status": status, "note": note}]
        return run_result_checks(plan, result, derived).verdict

    assert verdict("input_unreported", "the value for '2021-22' is not reported") == (
        "pass_with_caveats"
    )
    assert verdict("undefined", "") == "pass_with_caveats"
    assert verdict("input_unreported", f"Kerala: {NOT_IN_RESULT}0 rows") == "query_fault"
    assert verdict("incompatible_inputs", "base years differ") == "data_absent"


def test_place_check_reads_entity_alias_and_state_column() -> None:
    plan = stub_plan("demo").model_copy(update={"places": [_place("Wayanad")], "periods": []})
    result = QueryResult.model_validate(
        {
            "sql": "SELECT geo_name AS entity, geo_state, value FROM obs_demo",
            "columns": [
                {"name": "entity", "type": "VARCHAR"},
                {"name": "geo_state", "type": "VARCHAR"},
                {"name": "value", "type": "DOUBLE"},
            ],
            "rows": [["Wayanad", "Kerala", 1.0]],
            "row_count": 1,
            "truncated": False,
            "dataset_versions": {},
            "exec_ms": 1,
        }
    )
    places = next(o for o in run_intent_checks(plan, result) if o.name == "requested_places")
    assert places.passed


# Third batch: findings of the live smoke test of 18 November.


def test_bare_numbers_from_the_definition_are_not_claims() -> None:
    text = "Persons aged 15+ in Bihar: 5.1 percent in 2019-20."
    labels = ["Unemployment rate (%), usual status (ps+ss), persons aged 15+"]
    assert verify_numbers(text, [5.1], descriptors=labels).passed
    assert not verify_numbers("It was 15 percent.", [5.1], descriptors=labels).passed


def test_long_codelists_show_the_values_the_question_names() -> None:
    from analyst.tools.codelists import named_values

    values = ["Bhindi(Ladies Finger)", "Potato", "Wheat", "Onion"]
    assert named_values(values, "potato and ladies finger prices") == [
        "Bhindi(Ladies Finger)",
        "Potato",
    ]
    assert named_values(values, "Onionskin paper") == []


def test_coverage_reads_a_long_codelist_stored_as_a_count(tmp_path: Path, monkeypatch) -> None:
    from analyst.decisions import coverage

    monkeypatch.setattr(coverage, "codelist", lambda d, c: ["Paddy", "Wheat"])
    plan = stub_plan("msp").model_copy(
        update={"categories": {"commodity_name": ["Wheat"]}, "periods": [], "indicators": []}
    )
    table = {
        "dataset_id": "msp",
        "geo_levels": ["national"],
        "coverage_start": "2013-01-01",
        "coverage_end": "2025-12-31",
        "period_types": ["survey_year"],
        "indicator_units": {},
        "categories": {"commodity_name": 24},
    }
    assert coverage.check_coverage(plan, {"msp": table}).status == "covered"
    bad = plan.model_copy(update={"categories": {"commodity_name": ["Gold"]}})
    assert coverage.check_coverage(bad, {"msp": table}).status == "not_covered"


def test_execution_accuracy_projects_extra_columns() -> None:
    from analyst.evaluation.v0_eval import same_result, same_result_projected

    gold_sql = "SELECT geo_name AS entity, value FROM t"
    gold = [("Kerala", 9.6), ("Bihar", 5.9)]
    got = [("Bihar", "2021-22", "ur", 5.9, "percent"), ("Kerala", "2021-22", "ur", 9.6, "percent")]
    assert not same_result(gold_sql, got, gold)
    assert same_result_projected(gold_sql, got, gold)
    assert not same_result_projected(gold_sql, got[:1], gold)  # a missing row still fails
    wrong = [
        ("Bihar", "2021-22", "ur", 5.8, "percent"),
        ("Kerala", "2021-22", "ur", 9.6, "percent"),
    ]
    assert not same_result_projected(gold_sql, wrong, gold)


# Fourth batch: findings of the first e2e_dev run (v0, 18 November).


def test_number_parser_years_groupings_and_denominators() -> None:
    from analyst.tools.units import parse_numbers

    parsed = {m.text: m for m in parse_numbers("In 2023, 6,241,569.0 crimes; 448.3 per 100000")}
    assert parsed["2023"].is_period
    assert parsed["6,241,569.0"].value == Decimal("6241569.0")
    assert parsed["100000"].is_reference
    assert [m.text for m in parse_numbers("62,41,569 and 1,000")] == ["62,41,569", "1,000"]
    text = "Mizoram had 3.0 per 1,000 live births in 2019, the lowest."
    assert verify_numbers(text, [3.0]).passed
    assert not verify_numbers("Mizoram had 3.5 per 1,000 live births.", [3.0]).passed


def test_clarification_offers_the_tables_own_group(tmp_path: Path) -> None:
    from analyst.agents.tool_nodes import _clarify_options

    intent = _intent("clarify", "demo").model_copy(update={"indicator_ids": ["ur"]})
    table = {
        "dataset_id": "demo",
        "obs_table": "obs_demo",
        "indicator_units": {"ur": "percent"},
        "categories": {},
    }
    deps = ToolNodeDependencies(CATALOGUE, {}, lambda _d: _market_db(tmp_path))  # type: ignore[arg-type]
    options = _clarify_options("category", intent, table, deps)
    assert options == ["ur"]  # no observation file here, so the label falls back to the id


def test_answer_page_escapes_text_and_embeds_the_chart() -> None:
    from analyst.agents.answer_page import answer_page
    from analyst.contracts import ChartSpec

    spec = {"mark": "bar", "data": {"values": [{"a": "</script>"}]}}
    state = AnalystState(
        question="<b>Rain</b> in Kerala?",
        response_text="It rained.",
        chart=ChartSpec(chart_type="bar", decided_by="rules", reason="r", vega_lite=spec),
        result=_result([["Kerala", "2017-18", 10.0]]),
    )
    page = answer_page(state)
    assert "&lt;b&gt;Rain&lt;/b&gt;" in page and "<b>Rain" not in page
    assert "vegaEmbed('#chart'" in page and "<\\/script>" in page
    assert "Kerala" in page and "SELECT 1" in page


# Fifth batch: causes found in the first e2e_dev run.


def _plfs_like_db(tmp_path: Path) -> ReadOnlyDatabase:
    parquet = tmp_path / "obs_srs.parquet"
    pd.DataFrame(
        {
            "dataset_version": ["v1"] * 2,
            "geo_level": ["national", "state"],
            "geo_code": ["IN", "state:jammu_and_kashmir_including_ladakh"],
            "geo_name": ["India", "Jammu and Kashmir Including Ladakh"],
            "geo_vintage": ["2011", "2011"],
        }
    ).to_parquet(parquet)
    return ReadOnlyDatabase({"obs_srs": parquet})


def test_all_india_and_the_extended_state_name_resolve(tmp_path: Path) -> None:
    from analyst.tools.resolve import resolve_plan

    intent = _intent("answer", "srs").model_copy(
        update={"place_mentions": ["All India", "Jammu and Kashmir"]}
    )
    dataset = {"dataset_id": "srs", "dataset_version": "v1", "geo_levels": ["national", "state"]}
    plan = resolve_plan(
        intent, dataset=dataset, indicators=[], db=_plfs_like_db(tmp_path), refs={}, catalogue={}
    )
    assert [p.code for p in plan.places] == ["IN", "state:jammu_and_kashmir_including_ladakh"]
    assert not plan.unresolved
    assert any("Including Ladakh" in a.text for a in plan.assumptions)


def test_implausible_rows_are_a_query_fault_and_flags_become_caveats() -> None:
    from analyst.tools.checks import run_result_checks

    plan = stub_plan("demo").model_copy(update={"periods": [], "indicators": []})

    def result(flags: list[str]) -> QueryResult:
        return QueryResult.model_validate(
            {
                "sql": "SELECT 1",
                "columns": [
                    {"name": "value", "type": "DOUBLE"},
                    {"name": "quality_flag", "type": "?"},
                ],
                "rows": [[1.0, f] for f in flags],
                "row_count": len(flags),
                "truncated": False,
                "dataset_versions": {},
                "exec_ms": 1,
            }
        )

    bad = run_result_checks(plan, result(["reported", "implausible"]))
    assert bad.verdict == "query_fault" and "implausible" in (bad.retry_hint or "")
    flagged = run_result_checks(plan, result(["reported", "suppressed"]))
    assert flagged.verdict == "pass_with_caveats"
    assert [c.code for c in flagged.caveats] == ["suppressed"]


def test_scoring_reads_items_and_series_endpoints() -> None:
    from analyst.evaluation.e2e_eval import _case_checks

    case = {
        "expected_values": [1400.0, 1450.0, 1525.0, 2425.0],
        "actual_numbers": [1400.0, 1450.0, 1525.0, 2425.0],
        "narrated_numbers": [1400.0, 2425.0],
        "expected_entities": ["Wheat"],
        "actual_entities": ["Wheat"],
    }
    assert _case_checks(case) == {
        "values_match": True,
        "narration_match": True,
        "entity_match": True,
    }


def test_vertex_token_is_fetched_once_and_cached(monkeypatch) -> None:
    from analyst.inference import llm

    calls: list[int] = []
    monkeypatch.setattr(llm, "_TOKEN", {"value": None, "at": 0.0})
    monkeypatch.setattr(llm, "_fetch_gcloud_token", lambda: calls.append(1) or "tok")
    assert llm.gcloud_token() == "tok" and llm.gcloud_token() == "tok"
    assert len(calls) == 1


def test_national_question_keeps_total_rows_and_gets_the_latest_period(tmp_path: Path) -> None:
    from analyst.tools.resolve import resolve_plan

    parquet = tmp_path / "obs_srs.parquet"
    pd.DataFrame(
        {
            "dataset_version": ["v1"] * 2,
            "geo_level": ["national"] * 2,
            "geo_code": ["IN"] * 2,
            "geo_name": ["India"] * 2,
            "geo_vintage": ["2011"] * 2,
            "period_type": ["calendar_year"] * 2,
            "period_label": ["2018", "2019"],
            "period_start": pd.to_datetime(["2018-01-01", "2019-01-01"]),
            "period_end": pd.to_datetime(["2018-12-31", "2019-12-31"]),
        }
    ).to_parquet(parquet)
    intent = _intent("answer", "srs").model_copy(update={"place_mentions": ["all-India"]})
    dataset = {
        "dataset_id": "srs",
        "dataset_version": "v1",
        "geo_levels": ["national", "state"],
        "period_types": ["calendar_year"],
    }
    db = ReadOnlyDatabase({"obs_srs": parquet})
    plan = resolve_plan(intent, dataset=dataset, indicators=[], db=db, refs={}, catalogue={})
    assert plan.places[0].code == "IN" and plan.exclude_total_rows is False
    assert [p.label for p in plan.periods] == ["2019"]
    assert [a.code for a in plan.assumptions] == ["D1"]


def test_follow_up_keeps_the_prior_period_and_place() -> None:
    from analyst.agents.tool_nodes import inherit_from_prior

    prior = stub_plan("demo").model_copy(
        update={"places": [_place("Kerala")], "periods": [_window("2021-22", 2021)]}
    )
    latest = stub_plan("demo").model_copy(
        update={"periods": [_window("2022-23", 2022)], "places": []}
    )
    intent = _intent("answer", "demo").model_copy(update={"place_mentions": []})
    plan = inherit_from_prior(latest, intent, prior, CATALOGUE["demo"])
    assert [p.label for p in plan.periods] == ["2021-22"]
    assert [p.name for p in plan.places] == ["Kerala"]
    moved = intent.model_copy(update={"changed_slots": ["period"]})
    assert [
        p.label for p in inherit_from_prior(latest, moved, prior, CATALOGUE["demo"]).periods
    ] == ["2022-23"]


def test_clarify_without_a_table_becomes_a_clarification_not_a_decline(tmp_path: Path) -> None:
    from analyst.decisions.coverage import check_coverage

    nodes = make_tool_nodes(
        ToolNodeDependencies(CATALOGUE, {}, lambda _d: _market_db(tmp_path))  # type: ignore[arg-type]
    )
    intent = _intent("clarify", "none_fit").model_copy(
        update={"missing_slot": "period", "place_mentions": []}
    )
    plan = nodes["resolve_places_periods_units"](AnalystState(intent=intent))["plan"]
    assert [u.slot for u in plan.unresolved] == ["period"]
    assert check_coverage(plan, CATALOGUE).status == "ambiguous"


def test_cached_input_tokens_are_read_and_priced_at_ten_percent() -> None:
    from analyst.inference.llm import parse_reply

    payload = {
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 20000,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 18000},
        },
    }
    reply = parse_reply(payload, "m", 5)
    assert reply.cached_tokens == 18000
    from analyst.inference.scripted import scripted_client

    client, _ = scripted_client()  # input 0.1, output 0.4 USD per 1M tokens
    full, cached = client._cost(20000, 100), client._cost(20000, 100, 18000)
    assert full is not None and cached is not None
    assert abs(cached - (2000 * 0.1 + 1800 * 0.1 + 100 * 0.4) / 1e6) < 1e-12


def test_a_decline_with_a_named_table_states_the_intent_reason() -> None:
    # Dev run 3, e2e-085: "past month" when the CPI table ends in December 2023.
    from analyst.agents.nodes import decline_and_log_data_request
    from analyst.agents.state import AnalystState
    from analyst.contracts.coverage import CoverageResult, MissingPart

    intent = QueryIntent.model_validate(
        {
            "action": "decline",
            "dataset_id": "cpi_all_india",
            "indicator_ids": ["cpi_general_index"],
            "place_mentions": ["India"],
            "all_places_level": None,
            "period_mentions": [],
            "categories": {},
            "operation": "change",
            "order": None,
            "limit": None,
            "derivations": [],
            "changed_slots": [],
            "reason": "The CPI table ends in December 2023, so the past month is not covered.",
            "missing_slot": "period",
        }
    )
    coverage = CoverageResult.model_validate(
        {
            "status": "not_covered",
            "probability": None,
            "decided_by": "rules",
            "missing": [MissingPart(kind="indicator", detail="no table 'none_fit'")],
            "supported_plan": None,
            "left_out": [],
            "pointers": [],
        }
    )
    state = AnalystState(run_id="r1", question="q", intent=intent, coverage=coverage)
    text = decline_and_log_data_request(state)["response_text"]
    assert "none_fit" not in text
    assert "period (The CPI table ends in December 2023" in text
