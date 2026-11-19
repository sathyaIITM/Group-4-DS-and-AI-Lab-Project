"""Shared, deterministic metrics for model and end-to-end evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score


def accuracy(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float:
    """Return the share of exact label matches."""
    _same_length(y_true, y_pred)
    return float(np.mean(np.asarray(y_true, dtype=object) == np.asarray(y_pred, dtype=object)))


def accuracy_ci(
    correct: Sequence[bool | int], n_boot: int = 2000, seed: int = 0
) -> tuple[float, float]:
    """Return a percentile 95% bootstrap interval for a vector of per-case correctness flags."""
    values = np.asarray(correct, dtype=float)
    if values.ndim != 1 or not len(values):
        raise ValueError("correct must be a non-empty one-dimensional sequence")
    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    low, high = np.percentile(samples, [2.5, 97.5])
    return float(low), float(high)


def macro_f1(y_true: Sequence[Any], y_pred: Sequence[Any], labels: Sequence[Any]) -> float:
    """Return the unweighted mean of per-label F1 over the explicit label list."""
    _same_length(y_true, y_pred)
    scores = []
    for label in labels:
        tp = sum(a == label and b == label for a, b in zip(y_true, y_pred, strict=True))
        fp = sum(a != label and b == label for a, b in zip(y_true, y_pred, strict=True))
        fn = sum(a == label and b != label for a, b in zip(y_true, y_pred, strict=True))
        denom = 2 * tp + fp + fn
        scores.append(2 * tp / denom if denom else 0.0)
    if not scores:
        raise ValueError("labels must not be empty")
    return float(np.mean(scores))


def ece(
    confidence: Sequence[float] | np.ndarray,
    correct: Sequence[bool | int] | np.ndarray,
    n_bins: int = 10,
) -> float:
    """Expected calibration error using equal-width bins on [0, 1]."""
    _same_length(confidence, correct)
    conf = np.asarray(confidence, dtype=float)
    outcome = np.asarray(correct, dtype=float)
    _probabilities(conf, "confidence")
    if n_bins < 1:
        raise ValueError("n_bins must be positive")
    if not len(conf):
        raise ValueError("inputs must not be empty")
    if np.any((outcome != 0) & (outcome != 1)):
        raise ValueError("correct must contain only 0 or 1")
    bin_ids = np.minimum((conf * n_bins).astype(int), n_bins - 1)
    return float(
        sum(
            np.mean(bin_ids == index)
            * abs(outcome[bin_ids == index].mean() - conf[bin_ids == index].mean())
            for index in range(n_bins)
            if np.any(bin_ids == index)
        )
    )


def brier(prob_matrix: Sequence[Sequence[float]], y_true_index: Sequence[int]) -> float:
    """Multiclass Brier score: mean summed squared error from one-hot target vectors."""
    probs = np.asarray(prob_matrix, dtype=float)
    truth = np.asarray(y_true_index, dtype=int)
    if probs.ndim != 2 or probs.shape[0] != len(truth) or not len(truth):
        raise ValueError("probability rows and truth indices must have the same non-zero length")
    _probabilities(probs, "prob_matrix")
    if not np.allclose(probs.sum(axis=1), 1.0, rtol=1e-6, atol=1e-8):
        raise ValueError("each probability row must sum to 1")
    if np.any(truth < 0) or np.any(truth >= probs.shape[1]):
        raise ValueError("truth index is outside the probability columns")
    one_hot = np.eye(probs.shape[1], dtype=float)[truth]
    return float(np.square(probs - one_hot).sum(axis=1).mean())


def brier_binary(p: Sequence[float], y: Sequence[bool | int]) -> float:
    """Return the mean squared error of binary event probabilities."""
    _same_length(p, y)
    probs = np.asarray(p, dtype=float)
    truth = np.asarray(y, dtype=float)
    _probabilities(probs, "p")
    if np.any((truth != 0) & (truth != 1)):
        raise ValueError("y must contain only 0 or 1")
    return float(np.square(probs - truth).mean())


def auroc(score: Sequence[float], y: Sequence[bool | int]) -> float:
    """Return binary AUROC, as implemented by scikit-learn."""
    _same_length(score, y)
    return float(roc_auc_score(y, score))


def abstention_precision(non_answer: Sequence[bool], should_not_answer: Sequence[bool]) -> float:
    """Share of declined/withheld predictions that match gold non-answer cases; NaN if none."""
    _same_length(non_answer, should_not_answer)
    predicted = np.asarray(non_answer, dtype=bool)
    truth = np.asarray(should_not_answer, dtype=bool)
    count = int(predicted.sum())
    return float(np.logical_and(predicted, truth).sum() / count) if count else float("nan")


def abstention_recall(non_answer: Sequence[bool], should_not_answer: Sequence[bool]) -> float:
    """Share of gold non-answer cases correctly declined or withheld."""
    _same_length(non_answer, should_not_answer)
    predicted = np.asarray(non_answer, dtype=bool)
    truth = np.asarray(should_not_answer, dtype=bool)
    count = int(truth.sum())
    return float(np.logical_and(predicted, truth).sum() / count) if count else float("nan")


def latency_summary(ms: Sequence[float]) -> dict[str, float]:
    """Summarise latency samples in milliseconds as p50, p95 and maximum."""
    values = np.asarray(ms, dtype=float)
    if values.ndim != 1 or not len(values) or np.any(values < 0):
        raise ValueError("ms must be a non-empty sequence of non-negative values")
    return {
        "p50": round(float(np.percentile(values, 50)), 6),
        "p95": round(float(np.percentile(values, 95)), 6),
        "max": float(values.max()),
    }


def selective_accuracy(
    confidence: Sequence[float], correct: Sequence[bool | int], error_budget: float
) -> dict[str, float | None]:
    """Maximise answered share by descending confidence while respecting the error budget."""
    _same_length(confidence, correct)
    conf = np.asarray(confidence, dtype=float)
    outcome = np.asarray(correct, dtype=bool)
    _probabilities(conf, "confidence")
    if not 0 <= error_budget <= 1:
        raise ValueError("error_budget must be between 0 and 1")
    order = np.argsort(-conf, kind="stable")
    sorted_conf, sorted_outcome = conf[order], outcome[order]
    best_count, threshold = 0, None
    count = errors = 0
    index = 0
    while index < len(sorted_conf):
        score = sorted_conf[index]
        end = index
        while end < len(sorted_conf) and sorted_conf[end] == score:
            errors += int(not bool(sorted_outcome[end]))
            count += 1
            end += 1
        if errors / count <= error_budget:
            best_count, threshold = count, float(score)
        index = end
    return {"share": float(best_count / len(conf)), "threshold": threshold}


def execution_accuracy(
    results: Iterable[bool | tuple[str, list[tuple[Any, ...]], list[tuple[Any, ...]]]],
    projected: bool = False,
) -> float:
    """Share of correct flags or SQL result triples, using ``v0_eval.same_result`` for triples."""
    rows = list(results)
    if not rows:
        raise ValueError("results must not be empty")
    from analyst.evaluation.v0_eval import same_result, same_result_projected

    compare = same_result_projected if projected else same_result

    matches = []
    for result in rows:
        if isinstance(result, bool):
            matches.append(result)
        else:
            sql, actual, expected = result
            try:
                matches.append(compare(sql, actual, expected))
            except Exception:
                matches.append(False)
    return float(np.mean(matches))


def success_rate(cases: Sequence[bool | MappingLike]) -> float:
    """Share of cases marked handled correctly, or of boolean correctness flags."""
    if not cases:
        raise ValueError("cases must not be empty")
    correct = [
        bool(case.get("handled_correctly", case.get("correct", False)))
        if isinstance(case, dict)
        else bool(case)
        for case in cases
    ]
    return float(np.mean(correct))


MappingLike = dict[str, Any]


def _same_length(a: Sequence[Any] | np.ndarray, b: Sequence[Any] | np.ndarray) -> None:
    """Check that two inputs have the same, non-zero length."""
    if len(a) != len(b):
        raise ValueError("inputs must have the same length")
    if not len(a):
        raise ValueError("inputs must not be empty")


def _probabilities(value: np.ndarray, name: str) -> None:
    """Check that values are finite probabilities."""
    if np.any(~np.isfinite(value)) or np.any((value < 0) | (value > 1)):
        raise ValueError(f"{name} values must be finite and in [0, 1]")
