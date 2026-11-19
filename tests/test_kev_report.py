"""Tests for the Milestone 4 records of the Kev runs: coverage and the selection rule."""

import json
from pathlib import Path

from analyst.decisions import phase1
from analyst.decisions.kev_questions import QUESTIONS
from analyst.models import kev_report

ELIGIBLE = {"b0_s0", "b0_s1", "b0_s2", "lr4e-05"}


def _row(run_id: str, nll: float, f1: float = 0.8, factor: str = "lr") -> dict:
    return {"run_id": run_id, "factor": factor, "dev_nll": nll, "dev_macro_f1": f1}


def test_selection_keeps_b0_within_the_seed_spread() -> None:
    rows = [
        _row("b0_s0", 0.30, factor="b0"),
        _row("b0_s1", 0.34, factor="seed"),
        _row("b0_s2", 0.32, factor="seed"),
        _row("lr4e-05", 0.29),
    ]
    result = kev_report.select(rows, ELIGIBLE)
    assert result["noise_floor"] == 0.34 - 0.30
    assert result["other_replaces_b0"] is False
    assert result["decision"] == "b0_s0"


def test_selection_takes_a_clearly_better_setting() -> None:
    rows = [
        _row("b0_s0", 0.30, factor="b0"),
        _row("b0_s1", 0.31, factor="seed"),
        _row("b0_s2", 0.32, factor="seed"),
        _row("lr4e-05", 0.20),
    ]
    assert kev_report.select(rows, ELIGIBLE)["decision"] == "lr4e-05"


def test_selection_ignores_runs_outside_the_plan() -> None:
    rows = [
        _row("b0_s0", 0.30, factor="b0"),
        _row("b0_s1", 0.31, factor="seed"),
        _row("b0_s2", 0.32, factor="seed"),
        _row("zeroshot_v2", 0.01, factor="other"),
    ]
    result = kev_report.select(rows, ELIGIBLE)
    assert result["decision"] == "b0_s0" and "zeroshot_v2" in result["excluded"]


def test_selection_needs_three_seeds() -> None:
    assert kev_report.select([_row("b0_s0", 0.3, factor="b0")], ELIGIBLE)["decision"] is None


def test_target_table_from_template() -> None:
    assert kev_report.target_table({"template_id": "table.msp_crops.value.0"}) == "msp_crops"
    assert kev_report.target_table({"template_id": "describe.cpi_all_india.fixed.0"}) == (
        "cpi_all_india"
    )
    assert kev_report.target_table({"template_id": "imd.no_place.0"}) == (
        "imd_subdivision_monthly_rainfall"
    )
    assert kev_report.target_table({"template_id": "teacher"}) is None


def test_split_coverage_counts_tables_and_labels(tmp_path: Path) -> None:
    record = {
        "state": {"catalogue": "1. msp_crops: MSP\n2. cpi_all_india: CPI", "user_message": "x"},
        "questions": {"domain": {"label": "agriculture"}, "tool": {"label": "run_sql"}},
        "_meta": {"template_id": "table.msp_crops.value.0", "label_source": "rule"},
    }
    path = tmp_path / "train.v2.jsonl"
    path.write_text(json.dumps(record) + "\n")
    result = kev_report.split_coverage(path, {"msp_crops": "agriculture", "cpi_all_india": "p"})
    assert result["tables"]["msp_crops"]["named_by_template"] == 1
    assert result["tables"]["msp_crops"]["top1_candidate"] == 1
    assert result["tables"]["cpi_all_india"]["shown_in_top4"] == 1
    assert result["tables_not_named"] == ["cpi_all_india"]


def test_dev_human_record_uses_canonical_questions() -> None:
    row = {"id": "dh-001", "state": {"user_message": "x"}, "tool": "run_sql", "domain": "labour"}
    record = phase1.dev_human_record(row)
    assert record["_meta"]["id"] == "dh-001"
    for decision in ("tool", "domain"):
        instructions, criteria = QUESTIONS[decision]
        assert record["questions"][decision]["instructions"] == instructions
        assert record["questions"][decision]["criteria"] == criteria
    assert record["questions"]["domain"]["label"] == "labour"
