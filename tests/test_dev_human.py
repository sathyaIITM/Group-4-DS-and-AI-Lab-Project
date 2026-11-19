"""Tests for the dev_human overlap check, agreement, adjudication and freeze."""

import csv
from pathlib import Path

import pytest

from analyst.evaluation import dev_human as dh


def _write_labels(path: Path, rows: list[tuple]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(dh.LABEL_COLUMNS)
        writer.writerows(rows)


def test_blocks_cover_200_items_with_three_roles() -> None:
    covered = [n for b in dh.BLOCKS for n in range(b.first, b.last + 1)]
    assert covered == list(range(1, 201))
    for block in dh.BLOCKS:
        assert block.adjudicator not in block.labellers
    assert dh.block_of("dh-067").name == "A"
    assert dh.block_of("dh-068").name == "B"
    with pytest.raises(ValueError):
        dh.item_number("x-1")


def test_overlap_flags_near_duplicates_only() -> None:
    items = [
        {"id": "dh-001", "message": "What was the unemployment rate in Kerala in 2019-20?"},
        {"id": "dh-002", "message": "how wet was vidarbha during the last monsoon"},
    ]
    refs = {"train": ["What was the unemployment rate in Kerala in 2018-19?", "Hello"]}
    result = dh.overlap(items, refs)
    assert [r["id"] for r in result["flagged"]] == ["dh-001"]  # digits are mapped to 0
    assert result["flagged"][0]["jaccard"] == 1.0


def test_read_labels_validates_options_and_columns(tmp_path: Path) -> None:
    good = tmp_path / "labels_T1.csv"
    _write_labels(good, [("dh-001", "run_sql", "labour", "R6", "false", "")])
    assert dh.read_labels(good)["dh-001"]["tool"] == "run_sql"
    bad = tmp_path / "labels_T2.csv"
    _write_labels(bad, [("dh-001", "run_query", "labour", "R6", "false", "")])
    with pytest.raises(ValueError, match="not an option"):
        dh.read_labels(bad)
    undecided = tmp_path / "labels_T4.csv"
    _write_labels(undecided, [("dh-001", "", "", "", "true", "no rule decides")])
    assert dh.read_labels(undecided)["dh-001"]["undecided"]


def _label(tool: str, domain: str, undecided: bool = False) -> dict:
    return {"tool": tool, "domain": domain, "rule": "R6", "undecided": undecided, "note": ""}


def test_agreement_disagreements_and_freeze(tmp_path: Path) -> None:
    labels = {
        "T1": {
            "dh-001": _label("run_sql", "labour"),
            "dh-002": _label("run_sql", "rainfall"),
            "dh-003": _label("search_catalog", "health"),
        },
        "T2": {
            "dh-001": _label("run_sql", "labour"),
            "dh-002": _label("ask_clarification", "rainfall"),
            "dh-003": _label("", "", undecided=True),
        },
    }
    result = dh.agreement(labels)
    block = result["blocks"]["A"]
    assert block["items_labelled_by_both"] == 3
    assert block["undecided"] == 1
    assert block["tool"]["n"] == 2
    assert block["domain"]["agreement"] == 1.0

    rows = dh.disagreements(labels)["T4"]
    assert {(r["item_id"], r["decision"]) for r in rows} == {
        ("dh-002", "tool"),
        ("dh-003", "tool"),
        ("dh-003", "domain"),
    }
    rows[0]["final_label"] = "run_sql"  # dh-002 tool adjudicated
    rows[1]["ambiguous"] = "true"  # dh-003 removed
    final, ambiguous, unresolved = dh.final_labels(labels, rows, ["dh-001", "dh-002", "dh-003"])
    assert final == {
        "dh-001": {"tool": "run_sql", "domain": "labour"},
        "dh-002": {"tool": "run_sql", "domain": "rainfall"},
    }
    assert ambiguous == ["dh-003"]
    assert unresolved == []

    intended = tmp_path / "intended_labels.csv"
    with intended.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item_id", "tool", "domain"])
        writer.writerow(["dh-001", "run_sql", "labour"])
        writer.writerow(["dh-002", "ask_clarification", "rainfall"])
    diagnostic = dh.compare_intended(final, intended)
    assert diagnostic["tool"]["differ"] == 1
    assert diagnostic["domain"]["differ"] == 0


def test_unadjudicated_items_block_the_freeze() -> None:
    labels = {
        "T1": {"dh-001": _label("run_sql", "labour")},
        "T2": {"dh-001": _label("run_sql", "health")},
    }
    _, _, unresolved = dh.final_labels(labels, [], ["dh-001"])
    assert unresolved == ["dh-001"]


def test_missing_items_lists_each_labellers_blocks() -> None:
    todo = dh.missing_items({"T1": {"dh-001": _label("run_sql", "labour")}}, ["dh-001", "dh-100"])
    assert todo == {"T1": [], "T2": ["dh-001", "dh-100"], "T4": ["dh-100"]}
