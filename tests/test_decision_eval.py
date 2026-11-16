"""Tests for the Milestone 4 decision evaluation (gate, cascade, flips, figures)."""

from pathlib import Path

import numpy as np
import pytest

from analyst.evaluation import decision_eval as de

LABELS = de.labels_of("domain")


def _rows(n: int, accuracy: float, confidence: float, seed: int = 1, prefix: str = "r") -> list:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        truth = LABELS[i % len(LABELS)]
        wrong = LABELS[(i + 1) % len(LABELS)]
        top = truth if rng.random() < accuracy else wrong
        rest = (1 - confidence) / (len(LABELS) - 1)
        rows.append(
            {
                "id": f"{prefix}{i}",
                "label": truth,
                "predicted": top,
                "probabilities": {x: confidence if x == top else rest for x in LABELS},
                "latency_s": 0.2,
                "cost_usd": 0.0,
            }
        )
    return rows


def test_question_order_changes_but_options_do_not() -> None:
    base = de.question_for("domain")
    shuffled = de.question_for("domain", order_seed=3)
    assert list(base.criteria) == list(LABELS)
    assert list(shuffled.criteria) != list(LABELS)
    assert shuffled.criteria == base.criteria


def test_score_reports_every_metric() -> None:
    result = de.score(_rows(400, 0.8, 0.8), LABELS)
    assert result["accuracy"] == pytest.approx(0.8, abs=0.06)
    assert result["ece"] < 0.06
    assert set(result["per_label_f1"]) == set(LABELS)
    assert result["auroc_correct"] is not None
    assert sum(b["n"] for b in result["reliability"]) == 400
    assert result["cost_usd_per_1000"] == 0.0


def test_auroc_is_none_when_all_correct() -> None:
    assert de.auroc_of_correctness(np.array([0.9, 0.8]), np.array([1.0, 1.0])) is None


def test_temperature_lowers_ece_for_an_overconfident_model() -> None:
    cal, dev = _rows(400, 0.6, 0.95, seed=1), _rows(400, 0.6, 0.95, seed=2, prefix="d")
    report = de.calibrated_report(cal, dev, LABELS)
    assert report["dev_calibrated"]["ece"] < report["dev_raw"]["ece"]
    assert report["fitted_temperature"] > 1.0


def test_gate_passes_an_equal_model_and_fails_a_worse_one() -> None:
    jev = _rows(300, 0.85, 0.85, seed=5)
    same = de.gate(_rows(300, 0.85, 0.85, seed=6), _rows(300, 0.85, 0.85, seed=5), jev, LABELS)
    assert same["passes_point_estimate"]
    worse = de.gate(_rows(300, 0.6, 0.6, seed=6), _rows(300, 0.6, 0.6, seed=7), jev, LABELS)
    assert not worse["passes_point_estimate"]
    assert not worse["passes_non_inferiority"]


def test_align_rejects_disagreeing_labels() -> None:
    a = _rows(5, 1.0, 0.9)
    b = [dict(r) for r in a]
    b[0]["label"] = LABELS[-1] if a[0]["label"] != LABELS[-1] else LABELS[0]
    with pytest.raises(ValueError, match="labels differ"):
        de.align(a, b)


def test_choose_threshold_respects_the_error_budget() -> None:
    confidence = np.array([0.99, 0.95, 0.9, 0.7, 0.6, 0.5])
    correct = np.array([1, 1, 1, 0, 1, 0], float)
    assert de.choose_threshold(confidence, correct, 0.05) == 0.9
    assert de.choose_threshold(np.array([0.9]), np.array([0.0]), 0.05) == 1.01


def test_cascade_beats_kev_alone_when_jev_is_better() -> None:
    rng = np.random.default_rng(0)
    kev = []
    for i in range(400):  # confident when right, unsure when wrong
        truth = LABELS[i % len(LABELS)]
        right = rng.random() < 0.7
        top = truth if right else LABELS[(i + 1) % len(LABELS)]
        conf = 0.95 if right else 0.4
        rest = (1 - conf) / (len(LABELS) - 1)
        kev.append(
            {
                "id": f"r{i}",
                "label": truth,
                "predicted": top,
                "probabilities": {x: conf if x == top else rest for x in LABELS},
                "latency_s": 0.1,
            }
        )
    jev = _rows(400, 0.95, 0.9, seed=9)
    result = de.cascade(kev, kev, jev, LABELS)
    assert 0.5 < result["kev_share"] < 0.9
    assert result["cascade_accuracy"] > result["kev_only_accuracy"]


def test_flip_rate_counts_changed_predictions() -> None:
    a = [{"id": "x", "predicted": "labour"}, {"id": "y", "predicted": "health"}]
    b = [{"id": "x", "predicted": "labour"}, {"id": "y", "predicted": "other"}]
    assert de.flip_rate([a, b])["flip_rate"] == 0.5
    with pytest.raises(ValueError):
        de.flip_rate([a])


def test_reliability_figure_is_written(tmp_path: Path) -> None:
    result = de.score(_rows(100, 0.8, 0.8), LABELS)
    path = tmp_path / "rel.png"
    de.plot_reliability({"raw": result}, path, "test")
    assert path.stat().st_size > 1000
