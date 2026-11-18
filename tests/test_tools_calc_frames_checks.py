from __future__ import annotations

import duckdb
import pytest

from analyst.contracts.intent import QueryIntent
from analyst.tools.calc import cagr, difference_is_clear, mean, pct_change, rank, share
from analyst.tools.checks import run_statistical_checks
from analyst.tools.frames import cap_rows, join_denominator, pivot, top_k
from analyst.tools.numbers import verify_numbers
from analyst.tools.resolve import resolve_plan


def test_calculations_have_explicit_zero_and_tie_behaviour() -> None:
    assert pct_change(110, 100) == 10
    assert pct_change(1, 0) is None
    assert share(1, 0) is None
    assert cagr(100, 121, 2) == pytest.approx(10)
    assert rank([5, 5, 3]) == [1, 1, 3]
    assert mean([2, 4], [1, 3]) == pytest.approx(3.5)
    assert not difference_is_clear(10, 10.1, {"different_units": True})


def test_frame_ops_are_bounded_and_validate_joins() -> None:
    rows = [{"state": "A", "year": 2020, "value": 4}, {"state": "B", "year": 2020, "value": 8}]
    assert top_k(rows, 1, "value").iloc[0]["state"] == "B"
    assert pivot(rows, index="state", columns="year", values="value").shape == (2, 2)
    joined = join_denominator(rows, [{"state": "A", "population": 10}], on="state")
    assert joined.iloc[0]["population"] == 10
    with pytest.raises(ValueError):
        join_denominator(
            rows, [{"state": "A", "population": 1}, {"state": "A", "population": 2}], on="state"
        )
    with pytest.raises(ValueError):
        cap_rows(rows, 1001)


def test_number_check_ignores_periods_and_matches_evidence() -> None:
    result = verify_numbers("In 2020-21 the total was 12.5 lakh.", [1_250_000])
    assert result.passed
    assert not verify_numbers("The total was 15.", [12]).passed


def test_statistical_checks_flag_invalids_and_extremes() -> None:
    findings = run_statistical_checks([1, 2, 3, 4, 100], expected_non_negative=True)
    assert any(item["check"] == "extreme_outlier_review" for item in findings)
    assert any(
        item["check"] == "non_negative"
        for item in run_statistical_checks([-1], expected_non_negative=True)
    )


def test_resolve_plan_uses_catalogue_and_keeps_unknowns_unresolved() -> None:
    db = duckdb.connect(":memory:")
    db.execute(
        "CREATE TABLE obs_x (dataset_version VARCHAR, geo_level VARCHAR, geo_code VARCHAR, "
        "geo_name VARCHAR, geo_vintage VARCHAR)"
    )
    db.execute("INSERT INTO obs_x VALUES ('v1','state','01','Kerala','2020')")
    intent = QueryIntent(
        action="answer",
        dataset_id="x",
        indicator_ids=["rain"],
        place_mentions=["Kerala", "Keral"],
        all_places_level=None,
        period_mentions=[],
        categories={},
        operation="lookup",
        order=None,
        limit=None,
        derivations=[],
        changed_slots=[],
        reason=None,
    )
    plan = resolve_plan(
        intent,
        dataset={"dataset_id": "x", "geo_levels": ["state"]},
        indicators=[{"indicator_id": "rain", "label": "Rainfall", "unit": "mm"}],
        db=db,
        refs={},
        catalogue={"x": {"period_types": []}},
    )
    assert plan.places[0].name == "Kerala"
    assert {slot.mention for slot in plan.unresolved} == {"Keral"}
    assert plan.dataset_version == "v1"
    db.close()
