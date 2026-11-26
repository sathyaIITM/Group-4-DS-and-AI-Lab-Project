"""Tests for scorer v3 (`analyst.evaluation.scorer_v3`) and its use in `e2e_eval`."""

import json
from pathlib import Path
from typing import Any

import pytest

from analyst.evaluation import e2e_eval, scorer_v3


def _answer_case(**changes: Any) -> dict[str, Any]:
    """A correct answer record for a two-value comparison, as written from Milestone 5 on."""
    case: dict[str, Any] = {
        "id": "e2e-900",
        "expected_action": "answer",
        "outcome": "answered",
        "dataset_ids": ["plfs_state_ur_usual_status"],
        "expected_values": [10.0, 4.8],
        "expected_entities": ["Kerala", "India"],
        "tolerance": 0.005,
        "actual_numbers": [10.0, 4.8],
        "narrated_numbers": [10.0, 4.8],
        "actual_entities": ["Kerala", "India"],
        "number_check_passed": True,
        "response": "Kerala's unemployment rate was 10.0% in 2019-20, against 4.8% for India.",
        "result_columns": ["entity", "value"],
        "result_rows": [["Kerala", 10.0], ["India", 4.8]],
        "expected_places": [
            {"name": "Kerala", "level": "state"},
            {"name": "India", "level": "national"},
        ],
        "expected_periods": [{"start": "2019-07-01", "end": "2020-06-30"}],
        "indicator_ids": ["ur_usual_ps_ss"],
        "unit": "percent",
        "n_values": 2,
        "gold_lineage": "rows",
        "plan_places": [
            {"name": "Kerala", "level": "state"},
            {"name": "India", "level": "national"},
        ],
        "plan_all_places_level": None,
        "plan_periods": [{"start": "2019-07-01", "end": "2020-06-30", "label": "2019-20"}],
        "plan_indicators": ["ur_usual_ps_ss"],
        "evidence": {
            "dataset_ids": ["plfs_state_ur_usual_status"],
            "has_source": True,
            "sql": "SELECT 1",
        },
        "chart_attached": False,
        "clarify_slots_asked": [],
        "clarify_options_asked": [],
    }
    case.update(changes)
    return case


@pytest.fixture(autouse=True)
def _v3_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e2e_eval, "SCORER_RULES", "v3")


def test_correct_answer_passes_every_check() -> None:
    checks = e2e_eval.v3_checks(_answer_case())
    assert checks["action"] and checks["interpretation"] and checks["values"]
    assert checks["completeness"] and checks["unit"] and checks["period"] and checks["evidence"]
    assert checks["clarify_slot"] is None and checks["content"] is None
    assert e2e_eval._case_success(_answer_case())


@pytest.mark.parametrize(
    ("changes", "failed"),
    [
        ({"plan_places": [{"name": "Kerala", "level": "state"}]}, "interpretation"),
        (
            {"plan_periods": [{"start": "2020-07-01", "end": "2021-06-30", "label": "2020-21"}]},
            "interpretation",
        ),
        ({"plan_indicators": ["lfpr"]}, "interpretation"),
        ({"narrated_numbers": [10.0]}, "completeness"),
        ({"response": "Kerala's rate was 10.0 in 2019-20, against 4.8 for India."}, "unit"),
        ({"response": "Kerala's unemployment rate was 10.0%, against 4.8% for India."}, "period"),
        (
            {"evidence": {"dataset_ids": ["srs_imr_state"], "has_source": True, "sql": "x"}},
            "evidence",
        ),
        (
            {
                "evidence": {
                    "dataset_ids": ["plfs_state_ur_usual_status"],
                    "has_source": False,
                    "sql": "x",
                }
            },
            "evidence",
        ),
    ],
)
def test_each_check_fails_on_its_own(changes: dict[str, Any], failed: str) -> None:
    checks = e2e_eval.v3_checks(_answer_case(**changes))
    assert checks[failed] is False
    assert not e2e_eval._case_success(_answer_case(**changes))


def test_long_series_needs_both_ends_and_a_chart() -> None:
    values = [9.4, 9.0, 10.5, 11.0, 10.1]
    base = {
        "expected_values": values,
        "actual_numbers": values,
        "expected_entities": [],
        "narrated_numbers": [9.4, 10.1],
    }
    assert scorer_v3.check_completeness(
        _answer_case(**base, chart_attached=True), e2e_eval._within_tolerance
    )
    assert not scorer_v3.check_completeness(_answer_case(**base), e2e_eval._within_tolerance)


def test_whole_level_plan_covers_ranked_places() -> None:
    case = _answer_case(
        plan_places=[],
        plan_all_places_level="state",
        expected_places=[{"name": "Goa", "level": "state"}, {"name": "Nagaland", "level": "state"}],
    )
    assert scorer_v3.check_interpretation(case)
    assert not scorer_v3.check_interpretation({**case, "plan_all_places_level": "district"})


def test_range_window_covers_gold_periods() -> None:
    case = _answer_case(
        plan_periods=[{"start": "2017-07-01", "end": "2022-06-30", "label": "2017-18 to 2021-22"}],
        expected_periods=[
            {"start": "2017-07-01", "end": "2018-06-30"},
            {"start": "2021-07-01", "end": "2022-06-30"},
        ],
    )
    assert scorer_v3._periods_match(case)


def test_no_place_filter_matches_a_national_only_gold() -> None:
    national = [{"name": "India", "level": "national"}]
    case = _answer_case(plan_places=[], plan_all_places_level=None, expected_places=national)
    assert scorer_v3._places_match(case)
    state = [{"name": "Kerala", "level": "state"}]
    assert not scorer_v3._places_match({**case, "expected_places": state})


def test_range_planned_as_end_points_needs_every_value_in_the_result() -> None:
    years = [{"start": f"{y}-06-01", "end": f"{y}-09-30"} for y in range(2011, 2017)]
    ends = [years[0], years[-1]]
    case = _answer_case(
        plan_periods=ends,
        expected_periods=years,
        expected_values=[1167.0, 1153.3, 1115.6, 1255.7, 1034.5, 1031.5],
        actual_numbers=[1167.0, 1153.3, 1115.6, 1255.7, 1034.5, 1031.5],
    )
    match = lambda a, b, tol: abs(a - b) <= tol * max(1.0, abs(b))  # noqa: E731
    assert scorer_v3._periods_match(case, match)
    assert not scorer_v3._periods_match({**case, "actual_numbers": [1167.0, 1031.5]}, match)
    assert not scorer_v3._periods_match(case)  # no tolerance rule: strict windows only
    outside = {**case, "expected_periods": [*years, {"start": "2017-06-01", "end": "2017-09-30"}]}
    assert not scorer_v3._periods_match(outside, match)


def test_one_option_question_passes_only_for_a_single_gold_group() -> None:
    case = {
        "expected_action": "clarify",
        "outcome": "clarifying",
        "clarify_slot": "category",
        "clarify_slots_asked": ["category"],
        "clarify_options_asked": ["Unemployment rate, usual status (ps+ss), persons aged 15+"],
        "clarify_options": ["persons aged 15"],
    }
    assert scorer_v3.check_clarify_slot(case)  # E9c: the table's only group
    assert not scorer_v3.check_clarify_slot({**case, "clarify_options": None})  # D10
    two = ["Aurangabad (Bihar)", "Aurangabad (Maharashtra)"]
    assert not scorer_v3.check_clarify_slot({**case, "clarify_options": two})


def test_period_names() -> None:
    assert "2019-20" in scorer_v3.period_names("2019-07-01", "2020-06-30")
    assert "march 2021" in scorer_v3.period_names("2021-03-01", "2021-03-31")
    assert "2015" in scorer_v3.period_names("2015-01-01", "2015-12-31")
    assert "2019" in scorer_v3.period_names("2019-01-01", "2021-12-31")  # NFHS-5 round


def _clarify_case(**changes: Any) -> dict[str, Any]:
    case = {
        "id": "e2e-901",
        "expected_action": "clarify",
        "outcome": "clarifying",
        "clarify_slot": "place",
        "clarify_options": ["Aurangabad (Bihar)", "Aurangabad (Maharashtra)"],
        "clarify_slots_asked": ["place"],
        "clarify_options_asked": ["Aurangabad, Bihar", "Aurangabad, Maharashtra"],
        "plan_places": [],
        "plan_periods": [],
        "plan_indicators": [],
        "evidence": {},
    }
    case.update(changes)
    return case


def test_clarify_slot_and_options() -> None:
    assert scorer_v3.check_clarify_slot(_clarify_case())
    assert not scorer_v3.check_clarify_slot(_clarify_case(clarify_slots_asked=["period"]))
    assert not scorer_v3.check_clarify_slot(_clarify_case(clarify_options_asked=["Aurangabad"]))
    assert not scorer_v3.check_clarify_slot(
        _clarify_case(clarify_options_asked=["Bihar", "Maharashtra", "Gaya"][:1])
    )
    assert e2e_eval._case_success(_clarify_case())
    assert not e2e_eval._case_success(_clarify_case(outcome="declined"))


def test_old_records_are_not_scored_under_v3() -> None:
    old = {k: v for k, v in _answer_case().items() if k not in scorer_v3.V3_RECORD_FIELDS}
    with pytest.raises(ValueError, match="score it with --scorer v2"):
        e2e_eval._case_success(old)


def test_score_cases_reports_check_rates() -> None:
    report = e2e_eval.score_cases(
        [_answer_case(), _answer_case(id="e2e-902", narrated_numbers=[10.0])]
    )
    assert report["success_rate"] == 0.5
    assert report["checks_v3"]["completeness"] == {"n": 2, "pass_rate": 0.5}
    assert report["checks_v3"]["clarify_slot"]["n"] == 0


def test_apply_gold_replaces_the_gold_side_only() -> None:
    case = _answer_case(expected_action="decline", outcome="answered")
    item = {
        "id": "e2e-900",
        "expected_action": "answer",
        "dataset_ids": ["plfs_state_ur_usual_status"],
        "expected_values": [10.0, 4.8],
        "expected_entities": ["Kerala", "India"],
        "tolerance": 0.005,
        "notes": "",
        "gold_sql": None,
        "clarify_slot": None,
    }
    (updated,) = e2e_eval.apply_gold([case], [item])
    assert updated["expected_action"] == "answer" and updated["outcome"] == "answered"
    with pytest.raises(ValueError, match="without an item"):
        e2e_eval.apply_gold([case], [{**item, "id": "other"}])


def test_compare_runs_paired(tmp_path: Path) -> None:
    good = [_answer_case(id=f"e2e-{i}") for i in range(10)]
    bad = [
        _answer_case(id=f"e2e-{i}", narrated_numbers=[10.0]) if i < 6 else good[i]
        for i in range(10)
    ]
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text("".join(json.dumps(c) + "\n" for c in bad))
    b.write_text("".join(json.dumps(c) + "\n" for c in good))
    result = e2e_eval.compare_runs([a], [b], resamples=2000)
    assert result["difference_b_minus_a"] == pytest.approx(0.6)
    low, high = result["difference_ci95"]
    assert 0 < low <= 0.6 <= high
    assert result["mcnemar"] == {
        "only_a_succeeds": 0,
        "only_b_succeeds": 6,
        "p_value_exact": pytest.approx(0.03125),
    }


def test_compare_runs_only_ids(tmp_path: Path) -> None:
    a_cases = [_answer_case(id=f"e2e-{i}", narrated_numbers=[10.0]) for i in range(4)]
    b_cases = [_answer_case(id=f"e2e-{i}") for i in range(6)]
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text("".join(json.dumps(c) + "\n" for c in a_cases))
    b.write_text("".join(json.dumps(c) + "\n" for c in b_cases))
    with pytest.raises(ValueError, match="different items"):
        e2e_eval.compare_runs([a], [b], resamples=100)
    only = {f"e2e-{i}" for i in range(4)}
    result = e2e_eval.compare_runs([a], [b], resamples=100, only_ids=only)
    assert result["items"] == 4 and result["difference_b_minus_a"] == pytest.approx(1.0)
