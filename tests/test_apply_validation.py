"""Tests for `scripts/apply_validation.py` (ground-truth validation sheets)."""

import csv
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "apply_validation", ROOT / "scripts" / "apply_validation.py"
)
assert _spec and _spec.loader
av = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(av)

COLS = ["id", "field", "gold", "proposed", "rule", "note", "confidence", "decision", "decided_by"]


def _item(item_id: str, **changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": item_id,
        "expected_action": "answer",
        "expected_values": [3.0],
        "validated": False,
    }
    item.update(changes)
    return item


def _sheet(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLS)
        writer.writerows(rows)
        writer.writerow(["_summary", "", "", "", "", "2 rows", "", "", ""])
    return path


def _row(item_id: str, field: str, old: Any, new: Any, decision: str, by: str = "T1") -> list[str]:
    return [item_id, field, json.dumps(old), json.dumps(new), "V5", "", "high", decision, by]


def test_only_accepted_rows_change_items_in_every_file(tmp_path: Path) -> None:
    sheet = _sheet(
        tmp_path / "f.csv",
        [
            _row("e2e-1", "expected_values", [3.0], [3.0, 3.0], "accept"),
            _row("e2e-2", "expected_action", "answer", "decline", "reject"),
        ],
    )
    sets = {Path("a"): [_item("e2e-1"), _item("e2e-2")], Path("b"): [_item("e2e-1")]}
    log = av.apply(sets, av.read_rows(sheet), [], None)
    for items in sets.values():
        assert items[0]["expected_values"] == [3.0, 3.0]
        assert items[0]["gold_version"] == 2
        assert items[0]["gold_changes"][0]["decided_by"] == "T1"
        assert items[0]["validated"] is False
    assert sets[Path("a")][1]["expected_action"] == "answer"
    assert "gold_version" not in sets[Path("a")][1]
    assert any("reject" in line for line in log)


def test_stale_sheet_and_missing_decider_are_errors(tmp_path: Path) -> None:
    stale = _sheet(tmp_path / "s.csv", [_row("e2e-1", "expected_values", [9.0], [1.0], "accept")])
    with pytest.raises(av.ValidationError, match="differs"):
        av.apply({Path("a"): [_item("e2e-1")]}, av.read_rows(stale), [], None)
    no_one = [_row("e2e-1", "expected_values", [3.0], [1.0], "accept", "")]
    nobody = _sheet(tmp_path / "n.csv", no_one)
    with pytest.raises(av.ValidationError, match="decided_by"):
        av.read_rows(nobody)
    other = _sheet(tmp_path / "o.csv", [_row("e2e-9", "expected_values", [3.0], [1.0], "accept")])
    with pytest.raises(av.ValidationError, match="not in the given sets"):
        av.apply({Path("a"): [_item("e2e-1")]}, av.read_rows(other), [], None)


def test_validated_mark_needs_every_row_decided(tmp_path: Path) -> None:
    open_sheet = _sheet(tmp_path / "u.csv", [_row("e2e-1", "expected_values", [3.0], [1.0], "")])
    sets = {Path("a"): [_item("e2e-1"), _item("e2e-2")]}
    with pytest.raises(av.ValidationError, match="undecided"):
        av.apply(sets, av.read_rows(open_sheet), [], "T1")
    done = _sheet(tmp_path / "d.csv", [_row("e2e-1", "expected_values", [3.0], [3.0], "accept")])
    av.apply(sets, av.read_rows(done), [], "T1")
    assert all(i["validated"] and i["validated_by"] == "T1" for i in sets[Path("a")])
    assert "gold_changes" not in sets[Path("a")][0]  # a confirmed row changes nothing


def test_fields_sheet_sets_hand_filled_fields(tmp_path: Path) -> None:
    path = tmp_path / "g.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["id", "domain", "clarify_slot", "clarify_options", "rule", "decision", "decided_by"]
        )
        options = '["A (Bihar)", "A (Maharashtra)"]'
        writer.writerow(["e2e-1", "health", "place", options, "S2", "accept", "T3"])
        writer.writerow(["e2e-2", "labour", "", "", "M1", "", ""])
    sets = {Path("a"): [_item("e2e-1"), _item("e2e-2")]}
    av.apply(sets, [], av.read_rows(path), None)
    first, second = sets[Path("a")]
    assert (first["domain"], first["clarify_slot"]) == ("health", "place")
    assert first["clarify_options"] == ["A (Bihar)", "A (Maharashtra)"]
    assert "domain" not in second


# Change sheets only; `rule_gaps_draft.csv` holds rule decisions, not item changes.
DRAFTS = sorted(
    p
    for p in (ROOT / "data" / "eval" / "validation").glob("*_draft.csv")
    if p.name != "rule_gaps_draft.csv"
)


@pytest.mark.parametrize("sheet", DRAFTS, ids=lambda p: p.name)
def test_committed_draft_sheets_match_the_sets(sheet: Path) -> None:
    """Every draft row names a real item; an undecided or rejected row's `gold` equals the item's
    current value, and an accepted row's `proposed` does (the sheet has been applied)."""
    items = {
        json.loads(line)["id"]: json.loads(line)
        for path in (ROOT / "data" / "eval").glob("e2e_*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rows = av.read_rows(sheet)
    if sheet.name == "gold_fields_draft.csv":
        assert {r["id"] for r in rows} <= set(items)
        return
    for row in rows:
        assert row["id"] in items, row["id"]
        expected = row["proposed"] if row["decision"] == "accept" else row["gold"]
        assert items[row["id"]].get(row["field"]) == json.loads(expected), row
