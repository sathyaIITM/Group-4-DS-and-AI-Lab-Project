from __future__ import annotations

import pytest

from analyst.ops.drift import compare_windows, ks_statistic, proportion_difference, psi_categorical


def test_distribution_statistics_are_finite_and_directional() -> None:
    assert psi_categorical(["a"] * 60, ["a"] * 60) == pytest.approx(0)
    assert ks_statistic([1.0] * 60, [2.0] * 60) == 1
    assert proportion_difference([False] * 60, [True] * 60)["difference"] == 1


def test_compare_windows_marks_small_windows_and_emits_review() -> None:
    report = compare_windows(
        [
            {"run_id": f"r{i}", "outcome": "answered", "cause": None, "question": "rain"}
            for i in range(60)
        ],
        [
            {
                "run_id": f"c{i}",
                "outcome": "failed",
                "cause": "sql_invalid",
                "question": "education transport",
            }
            for i in range(60)
        ],
        minimum=50,
    )
    signals = {signal["name"]: signal for signal in report["signals"]}
    assert signals["outcome:failed"]["verdict"] == "alert"
    assert signals["question_length"]["statistic"] > 0
    small = compare_windows([{"outcome": "answered"}] * 4, [{"outcome": "failed"}] * 4)
    assert all(signal["verdict"] == "insufficient_data" for signal in small["signals"])
