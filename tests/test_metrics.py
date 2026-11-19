"""Tests for the evaluation metrics."""

from __future__ import annotations

import math

import pytest

from analyst.evaluation.metrics import (
    abstention_precision,
    abstention_recall,
    accuracy,
    accuracy_ci,
    auroc,
    brier,
    brier_binary,
    ece,
    execution_accuracy,
    latency_summary,
    macro_f1,
    selective_accuracy,
    success_rate,
)


def test_accuracy_and_bootstrap_interval() -> None:
    assert accuracy(["a", "b", "a"], ["a", "a", "a"]) == pytest.approx(2 / 3)
    assert accuracy_ci([True, True, True], n_boot=100, seed=5) == (1.0, 1.0)


def test_macro_f1_includes_labels_with_no_true_positive() -> None:
    assert macro_f1(["a", "b"], ["a", "a"], ["a", "b"]) == pytest.approx(1 / 3)


def test_ece_calibration_and_confident_errors() -> None:
    assert ece([0.5, 0.5, 1.0], [1, 0, 1]) == 0
    assert ece([1.0, 1.0], [0, 0]) == 1


def test_brier_scores() -> None:
    assert brier([[1.0, 0.0], [0.0, 1.0]], [0, 1]) == 0
    assert brier([[0.8, 0.2]], [0]) == pytest.approx(0.08)
    assert brier_binary([0.8, 0.1], [1, 0]) == pytest.approx(0.025)


def test_auroc_hand_computed() -> None:
    assert auroc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)


def test_abstention_metrics_and_empty_precision() -> None:
    assert abstention_precision([True, True, False], [True, False, True]) == pytest.approx(0.5)
    assert abstention_recall([True, False, False], [True, True, False]) == pytest.approx(0.5)
    assert math.isnan(abstention_precision([False, False], [True, False]))


def test_latency_summary() -> None:
    assert latency_summary([1, 2, 3, 4]) == {"p50": 2.5, "p95": 3.85, "max": 4.0}


def test_selective_accuracy_obeys_budget_and_ties() -> None:
    assert selective_accuracy([0.9, 0.8], [True, True], 0)["share"] == 1.0
    assert selective_accuracy([0.9, 0.8, 0.8], [True, True, False], 0) == {
        "share": 1.0 / 3.0,
        "threshold": 0.9,
    }


def test_execution_accuracy_reuses_v0_result_comparison() -> None:
    rows = [
        ("SELECT x FROM t", [(1,), (2,)], [(2,), (1,)]),
        ("SELECT x FROM t ORDER BY x", [(2,), (1,)], [(1,), (2,)]),
    ]
    assert execution_accuracy(rows) == 0.5


def test_success_rate_uses_handled_correctly() -> None:
    assert success_rate(
        [True, {"handled_correctly": True}, {"handled_correctly": False}]
    ) == pytest.approx(2 / 3)


def test_input_validation() -> None:
    with pytest.raises(ValueError):
        accuracy([1], [1, 2])
    with pytest.raises(ValueError):
        ece([1.1], [True])
