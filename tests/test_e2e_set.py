"""Tests for the e2e_v1 validator (scripts/check_e2e_set.py) and the committed set."""

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SET_PATH = ROOT / "data" / "eval" / "e2e_v1.jsonl"
PROCESSED = ROOT / "data" / "processed"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_e2e_set", ROOT / "scripts" / "check_e2e_set.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()
needs_data = pytest.mark.skipif(
    not SET_PATH.exists() or not list(PROCESSED.glob("obs_*.parquet")),
    reason="published tables (data/processed/obs_*.parquet) or the e2e set are not present",
)


def _answer_item() -> dict:
    return {
        "id": "e2e-001",
        "question": "What was the MSP of wheat in 2022-23?",
        "prior_turns": [],
        "expected_action": "answer",
        "dataset_ids": ["msp_crops"],
        "gold_sql": "SELECT value FROM obs_msp_crops WHERE commodity_name = 'Wheat'",
        "expected_values": [2125.0],
        "expected_entities": [],
        "tolerance": 0.005,
        "expected_caveats": [],
        "operation": "lookup",
        "derivation": None,
        "conventions": [],
        "notes": "",
        "author": "T1",
        "validated": False,
        "written_on": "2026-11-17",
    }


def test_derive_formulas() -> None:
    assert checker.derive("difference", [4.0, 3.0]) == [-1.0]
    assert checker.derive("pct_change", [200.0, 210.0]) == [5.0]
    assert checker.derive("share_pct", [25.0, 200.0]) == [12.5]
    with pytest.raises(ValueError, match="unknown derivation"):
        checker.derive("ratio", [1.0, 2.0])


def test_close_is_relative_with_a_floor() -> None:
    assert checker.close(100.4, 100.0, 0.005)
    assert not checker.close(101.0, 100.0, 0.005)
    assert checker.close(0.0, 0.0, 0.0)


def test_shape_accepts_a_valid_item_and_rejects_faults() -> None:
    item = _answer_item()
    assert checker.check_shape(item) == []
    missing = copy.deepcopy(item)
    del missing["notes"]
    assert any("missing field notes" in e for e in checker.check_shape(missing))
    bad_action = {**item, "expected_action": "reply"}
    assert any("expected_action" in e for e in checker.check_shape(bad_action))
    bad_id = {**item, "id": "q-1"}
    assert any("id must look like" in e for e in checker.check_shape(bad_id))
    extra = {**item, "hint": "x"}
    assert any("unknown fields" in e for e in checker.check_shape(extra))


def test_action_rules() -> None:
    item = _answer_item()
    assert checker.check_action_rules(item) == []
    decline = {**item, "expected_action": "decline", "operation": "decline"}
    errors = checker.check_action_rules(decline)
    assert any("must not have gold_sql" in e for e in errors)
    assert any("empty dataset_ids" in e for e in errors)
    clarify = {
        **item,
        "expected_action": "clarify",
        "operation": "clarify",
        "gold_sql": None,
        "expected_values": [],
        "notes": "",
    }
    assert any("needs notes" in e for e in checker.check_action_rules(clarify))


@needs_data
def test_committed_set_passes_every_check() -> None:
    report = checker.run(SET_PATH, PROCESSED)
    assert report["errors"] == []
    summary = report["summary"]
    assert summary["items"] == 100
    assert summary["by_action"]["answer"] >= 70


@needs_data
def test_a_wrong_expected_value_is_reported(tmp_path: Path) -> None:
    rows = [json.loads(line) for line in SET_PATH.read_text(encoding="utf-8").splitlines()]
    target = next(r for r in rows if r["expected_action"] == "answer")
    target["expected_values"] = [v + 1000 for v in target["expected_values"]]
    mutated = tmp_path / "mutated.jsonl"
    mutated.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    errors = checker.run(mutated, PROCESSED)["errors"]
    assert any(e.startswith(target["id"]) and "differs from expected" in e for e in errors)


@needs_data
def test_sql_outside_dataset_ids_and_writes_are_reported(tmp_path: Path) -> None:
    rows = [json.loads(line) for line in SET_PATH.read_text(encoding="utf-8").splitlines()]
    answers = [r for r in rows if r["expected_action"] == "answer"]
    answers[0]["dataset_ids"] = (
        ["srs_imr_state"] if answers[0]["dataset_ids"] != ["srs_imr_state"] else ["msp_crops"]
    )
    answers[1]["gold_sql"] = "DELETE FROM obs_msp_crops"
    mutated = tmp_path / "mutated.jsonl"
    mutated.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    errors = checker.run(mutated, PROCESSED)["errors"]
    assert any(e.startswith(answers[0]["id"]) and "outside dataset_ids" in e for e in errors)
    assert any(e.startswith(answers[1]["id"]) and "gold_sql failed" in e for e in errors)
