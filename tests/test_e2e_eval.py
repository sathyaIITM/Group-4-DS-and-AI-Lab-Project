from __future__ import annotations

import json

import pytest

from analyst.evaluation.e2e_eval import run_evaluation, score_cases, score_repeats, split_items


def test_split_is_deterministic_stratified_and_complete() -> None:
    items = [
        {
            "id": f"e2e-{index:03}",
            "expected_action": "answer" if index % 3 else "decline",
            "dataset_ids": [f"table_{index % 4}"],
            "prior_turns": [],
        }
        for index in range(1, 101)
    ]
    dev, test = split_items(items, seed=13)
    dev_again, test_again = split_items(items, seed=13)
    assert len(dev) == 40 and len(test) == 60
    assert [row["id"] for row in dev] == [row["id"] for row in dev_again]
    assert [row["id"] for row in test] == [row["id"] for row in test_again]
    assert {row["id"] for row in dev}.isdisjoint(row["id"] for row in test)
    assert {row["id"] for row in dev + test} == {row["id"] for row in items}


def test_score_cases_enforces_answer_clarify_decline_and_dataset_rules() -> None:
    cases = [
        {
            "id": "good-answer",
            "expected_action": "answer",
            "outcome": "answered",
            "expected_values": [4.2],
            "actual_numbers": [4.2],
            "narrated_numbers": [4.2],
            "expected_entities": ["Jharkhand"],
            "actual_entities": ["Jharkhand"],
            "number_check_passed": True,
            "tolerance": 0.005,
            "duration_ms": 100,
            "first_event_ms": 2,
            "cost_usd_est": 0.01,
            "llm_calls": 2,
        },
        {
            "id": "bad-answer",
            "expected_action": "answer",
            "outcome": "answered",
            "expected_values": [9.0],
            "actual_numbers": [7.0],
            "narrated_numbers": [7.0],
            "expected_entities": ["Kerala"],
            "actual_entities": ["Kerala"],
            "number_check_passed": True,
            "tolerance": 0.005,
            "duration_ms": 200,
            "first_event_ms": 3,
            "cost_usd_est": 0.02,
            "llm_calls": 3,
        },
        {
            "id": "clarify",
            "expected_action": "clarify",
            "outcome": "clarifying",
            "notes": "Missing slot: survey year. Need an explicit year.",
            "unresolved_slots": ["period"],
        },
        {"id": "decline", "expected_action": "decline", "outcome": "declined"},
        {
            "id": "wrong-table",
            "expected_action": "describe",
            "outcome": "described",
            "dataset_ids": ["right"],
            "actual_dataset_ids": ["wrong"],
        },
    ]
    result = score_cases(cases)
    assert result["success_rate"] == pytest.approx(3 / 5)
    assert result["execution_accuracy"] == 0.0
    assert result["wrong_answer_rate"] == pytest.approx(1 / 2)
    assert result["outcome_counts"]["answered"] == 2
    assert result["cost_usd_est"] == pytest.approx(0.03)


def test_harness_rejects_more_than_two_workers_and_unvalidated_set(tmp_path) -> None:
    cases = [
        {
            "id": "e2e-001",
            "question": "Question?",
            "validated": False,
            "expected_action": "answer",
            "dataset_ids": ["demo"],
            "prior_turns": [],
            "expected_values": [1],
            "expected_entities": [],
            "tolerance": 0.005,
        }
    ]
    set_path = tmp_path / "set.jsonl"
    set_path.write_text(json.dumps(cases[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at most two"):
        run_evaluation(
            set_path,
            tmp_path / "out.jsonl",
            version="v2",
            experiment="x",
            member="T4",
            live=False,
            workers=3,
        )
    with pytest.raises(ValueError, match="unvalidated gold"):
        run_evaluation(
            set_path, tmp_path / "out.jsonl", version="v2", experiment="x", member="T4", live=False
        )


def test_score_repeats_reports_correctness_instability(tmp_path) -> None:
    baseline = {
        "id": "e2e-001",
        "expected_action": "answer",
        "outcome": "answered",
        "expected_values": [1],
        "actual_numbers": [1],
        "narrated_numbers": [1],
        "expected_entities": [],
        "actual_entities": [],
        "number_check_passed": True,
        "tolerance": 0.005,
        "duration_ms": 20,
        "first_event_ms": 1,
        "cost_usd_est": 0.1,
    }
    first, second = tmp_path / "run1.jsonl", tmp_path / "run2.jsonl"
    first.write_text(json.dumps(baseline) + "\n", encoding="utf-8")
    wrong = {**baseline, "outcome": "failed", "actual_numbers": []}
    second.write_text(json.dumps(wrong) + "\n", encoding="utf-8")
    report = score_repeats([first, second])
    assert report["items_changed_correctness"] == ["e2e-001"]
    assert report["run_to_run_instability"] == 1.0
