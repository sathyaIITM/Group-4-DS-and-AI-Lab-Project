"""Tests for the model-backed node functions: intent, coverage, SQL, narration, clarification."""

from datetime import date
from typing import Any

import pytest

from analyst.contracts.common import IndicatorRef, PeriodWindow, Place
from analyst.contracts.intent import DerivationRequest
from analyst.contracts.plan import InterpretationPlan, UnresolvedSlot
from analyst.contracts.sql import SqlDraft
from analyst.decisions import coverage as cov
from analyst.inference import clarify, intent, narrate, sqlgen
from analyst.inference.llm import LlmError
from analyst.inference.scripted import Counters, scripted_client

PLFS = "plfs_state_ur_usual_status"
CATALOGUE: dict[str, dict[str, Any]] = {
    PLFS: {
        "dataset_id": PLFS,
        "domain": "labour",
        "indicator_units": {"ur_usual_ps_ss": "percent"},
        "geo_levels": ["national", "state"],
        "coverage_start": "2017-07-01",
        "coverage_end": "2022-06-30",
        "period_types": ["survey_year"],
        "categories": {},
    },
    "imd_rain": {"dataset_id": "imd_rain", "domain": "rainfall", "indicator_units": {}},
    "nfhs": {"dataset_id": "nfhs", "domain": "health", "indicator_units": {}},
}
RETRIEVED = {
    "tables": [{"dataset_id": PLFS, "title": "PLFS unemployment", "geo_levels": ["state"]}],
    "indicators": [
        {"dataset_id": PLFS, "indicator_id": "ur_usual_ps_ss", "label": "UR", "unit": "percent"}
    ],
    "categories": {PLFS: {"sector": ["rural", "urban"]}},
    "cards": ["Usual status means ps+ss."],
}
INTENT = {
    "action": "answer",
    "dataset_id": PLFS,
    "indicator_ids": ["ur_usual_ps_ss"],
    "place_mentions": ["Kerala"],
    "all_places_level": None,
    "period_mentions": ["2019-20"],
    "categories": {},
    "operation": "lookup",
    "order": None,
    "limit": None,
    "derivations": [],
    "changed_slots": [],
    "reason": None,
}


def _period(label: str, start: date, end: date, kind: str = "survey_year") -> PeriodWindow:
    return PeriodWindow(requested=label, type=kind, label=label, start=start, end=end)


def _plan(**changes: Any) -> InterpretationPlan:
    base: dict[str, Any] = {
        "dataset_id": PLFS,
        "obs_table": f"obs_{PLFS}",
        "dataset_version": "1",
        "indicators": [IndicatorRef(indicator_id="ur_usual_ps_ss", label="UR", unit="percent")],
        "places": [
            Place(
                requested="Kerala", level="state", code="state:kerala", name="Kerala", match="exact"
            )
        ],
        "all_places_level": None,
        "periods": [_period("2019-20", date(2019, 7, 1), date(2020, 6, 30))],
        "categories": {},
        "operation": "lookup",
        "order": None,
        "limit": None,
        "derivations": [],
        "exclude_total_rows": True,
        "assumptions": [],
        "unresolved": [],
    }
    return InterpretationPlan(**(base | changes))


# ---------------------------------------------------------------------------- intent


def test_intent_accepts_retrieved_values() -> None:
    llm, transport = scripted_client(INTENT)
    result, record = intent.extract_intent(
        "Kerala unemployment 2019-20?", RETRIEVED, None, llm, Counters()
    )
    assert result.dataset_id == PLFS and record.node == "extract_query_intent"
    assert "Usual status means ps+ss." in transport.calls[0][1]


@pytest.mark.parametrize(
    "change",
    [
        {"dataset_id": "nfhs"},
        {"indicator_ids": ["lfpr"]},
        {"categories": {"sector": ["semi-urban"]}},
        {"dataset_id": "none_fit"},
        {"action": "decline", "reason": None, "dataset_id": "none_fit", "indicator_ids": []},
    ],
)
def test_intent_with_unretrieved_values_is_retried_then_fails(change: dict[str, Any]) -> None:
    llm, _ = scripted_client(INTENT | change, INTENT | change)
    with pytest.raises(LlmError) as caught:
        intent.extract_intent("q", RETRIEVED, None, llm, Counters())
    assert len(caught.value.records) == 2


# ---------------------------------------------------------------------------- coverage


def test_coverage_covered() -> None:
    result = cov.check_coverage(_plan(), CATALOGUE)
    assert result.status == "covered" and result.probability is None
    assert result.decided_by == "rules"


def test_coverage_partial_keeps_the_supported_periods() -> None:
    plan = _plan(
        periods=[
            _period("2019-20", date(2019, 7, 1), date(2020, 6, 30)),
            _period("2023-24", date(2023, 7, 1), date(2024, 6, 30)),
        ]
    )
    result = cov.check_coverage(plan, CATALOGUE)
    assert result.status == "partial"
    assert result.supported_plan is not None
    assert [p.label for p in result.supported_plan.periods] == ["2019-20"]
    assert result.left_out == ["period 2023-24"]
    assert cov.restrict(plan, result).status == "partial"


def test_coverage_not_covered_period_and_grain() -> None:
    late = _plan(periods=[_period("2023-24", date(2023, 7, 1), date(2024, 6, 30))])
    assert cov.check_coverage(late, CATALOGUE).status == "not_covered"
    monthly = _plan(periods=[_period("Jan 2020", date(2020, 1, 1), date(2020, 1, 31), "month")])
    result = cov.check_coverage(monthly, CATALOGUE)
    assert result.status == "not_covered" and result.missing[0].kind == "period"
    district = _plan(all_places_level="district", places=[])
    assert cov.check_coverage(district, CATALOGUE).missing[0].kind == "geo_level"


def test_coverage_unknown_table_points_to_related_tables() -> None:
    result = cov.check_coverage(_plan(dataset_id="groundwater"), CATALOGUE, domain="health")
    assert result.status == "not_covered" and result.pointers == ["nfhs"]


def test_per_capita_without_census_is_not_covered() -> None:
    plan = _plan(derivations=[DerivationRequest(op="per_capita", args={})])
    result = cov.check_coverage(plan, CATALOGUE)
    assert result.status == "not_covered"
    assert result.missing[0].kind == "population"
    with_census = CATALOGUE | {
        "census": {
            "dataset_id": "census",
            "domain": "other",
            "indicator_units": {"population_total": "persons"},
        }
    }
    assert cov.check_coverage(plan, with_census).status == "covered"


def test_unresolved_slot_is_ambiguous() -> None:
    plan = _plan(
        unresolved=[
            UnresolvedSlot(slot="place", mention="the south", options=["Kerala", "Tamil Nadu"])
        ]
    )
    assert cov.check_coverage(plan, CATALOGUE).status == "ambiguous"


# ---------------------------------------------------------------------------- SQL


def test_generate_sql_checks_the_table_and_strips_semicolon() -> None:
    good = {
        "sql": f"SELECT geo_name, value FROM obs_{PLFS} WHERE indicator_id='x';",
        "statement": "UR by state",
    }
    other = {"sql": "SELECT * FROM obs_imd_rain", "statement": "s"}
    llm, transport = scripted_client(other, good)
    draft, _ = sqlgen.generate_sql(
        _plan(), "geo_name VARCHAR", RETRIEVED, None, ["filter"], llm, Counters()
    )
    assert not draft.sql.endswith(";")
    assert len(transport.calls) == 2
    assert "filter" in transport.calls[0][1]


@pytest.mark.parametrize(
    "sql",
    [f"DELETE FROM obs_{PLFS}", f"SELECT 1 FROM obs_{PLFS}; DROP TABLE x", "SELECT 1"],
)
def test_check_draft_rejects(sql: str) -> None:
    with pytest.raises(ValueError):
        sqlgen.check_draft(SqlDraft(sql=sql, statement="s"), f"obs_{PLFS}")


def test_repair_sql() -> None:
    llm, _ = scripted_client({"sql": f"SELECT value FROM obs_{PLFS}", "statement": "s"})
    draft = SqlDraft(sql=f"SELECT valu FROM obs_{PLFS}", statement="s")
    repaired, record = sqlgen.repair_sql(
        draft, "unknown column valu", "value DOUBLE", f"obs_{PLFS}", llm, Counters()
    )
    assert repaired.sql.startswith("SELECT value") and record.node == "bounded_sql_repair"


# ---------------------------------------------------------------------------- narration


EVIDENCE = {
    "question": "Kerala UR 2019-20?",
    "result": {
        "columns": [{"name": "geo_name", "type": "VARCHAR"}, {"name": "value", "type": "DOUBLE"}],
        "rows": [["Kerala", 10.0]],
    },
    "derived": [{"id": "d1"}],
}


def _claim(cell: Any = None, derived: Any = None) -> dict[str, Any]:
    return {"text": "x", "numbers": [{"text": "10.0", "cell": cell, "derived_id": derived}]}


def test_narration_references_are_checked() -> None:
    good = {"text": "Kerala: 10.0 percent.", "claims": [_claim({"row": 0, "column": "value"})]}
    bad = {"text": "Kerala: 10.0 percent.", "claims": [_claim({"row": 3, "column": "value"})]}
    llm, _ = scripted_client(bad, good)
    narration, _ = narrate.narrate(EVIDENCE, None, llm, Counters(), attempt=2)
    assert narration.attempt == 2 and narration.claims[0].numbers[0].cell is not None


@pytest.mark.parametrize(
    "claim",
    [
        _claim(),
        _claim({"row": 0, "column": "value"}, "d1"),
        _claim(None, "d9"),
        _claim({"row": 0, "column": "unit"}),
    ],
)
def test_bad_references_are_rejected(claim: dict[str, Any]) -> None:
    reply = narrate.NarrationReply.model_validate({"text": "t", "claims": [claim]})
    with pytest.raises(ValueError):
        narrate.check_references(reply, EVIDENCE)


# ---------------------------------------------------------------------------- clarification


def test_clarification_rejects_invented_numbers() -> None:
    llm, _ = scripted_client(
        {"question": "Do you mean 2018-19 or 2025-26?"},
        {"question": "Which survey year: 2018-19 or 2019-20?"},
    )
    text, _ = clarify.write_clarification(
        "unemployment in 2019 (Jan-Dec)", "period", ["2018-19", "2019-20"], llm, Counters()
    )
    assert text == "Which survey year: 2018-19 or 2019-20?"


def test_regenerated_sql_uses_the_regeneration_level() -> None:
    good = {"sql": f"SELECT value FROM obs_{PLFS}", "statement": "s"}
    llm, transport = scripted_client(good, good)
    llm.thinking = {"sql": "minimal"}
    llm.thinking_on_regenerate = {"sql": "medium"}
    sqlgen.generate_sql(_plan(), "s", RETRIEVED, None, None, llm, Counters())
    sqlgen.generate_sql(
        _plan(), "s", RETRIEVED, "SELECT 1", ["fix"], llm, Counters(), regenerate=True
    )
    assert [r.reasoning_effort for r in transport.requests] == ["minimal", "medium"]


def test_intent_check_ignores_codelists_that_are_not_value_lists() -> None:
    retrieved = RETRIEVED | {"categories": {PLFS: {"sector": 3}}}  # a count, not a list
    llm, _ = scripted_client(INTENT | {"categories": {"sector": ["rural"]}}, INTENT)
    result, record = intent.extract_intent("q", retrieved, None, llm, Counters())
    assert result.categories == {}
    assert "not listed" in (record.earlier_attempts[0].parse_error or "")
