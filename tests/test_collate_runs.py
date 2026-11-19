"""Tests for collating exported run bundles into the warehouse."""

from __future__ import annotations

import hashlib
import json
import shutil

import pandas as pd

from analyst.ops.collate_runs import TABLE_KEYS, collate_bundles


def _bundle(path, run_payload: str) -> None:
    path.mkdir(parents=True)
    counts, hashes = {}, {}
    for table, key_columns in TABLE_KEYS.items():
        columns = [*key_columns, "payload"]
        rows = [["run-1", run_payload]] if table == "runs" else []
        frame = pd.DataFrame(rows, columns=columns)
        target = path / f"{table}.parquet"
        frame.to_parquet(target, index=False)
        counts[table] = len(frame)
        hashes[table] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {
        "member": "T4",
        "machine_id": "abc123",
        "schema_version": 1,
        "time_range": {"started_at_min": "2026-11-17T10:00:00Z"},
        "git_shas": ["1234567"],
        "row_counts": counts,
        "sha256": hashes,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_collator_is_idempotent_and_records_conflicts(tmp_path) -> None:
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    _bundle(bundles / "first", "original")
    _bundle(bundles / "second", "changed")
    shutil.copytree(bundles / "first", bundles / "duplicate")

    report = collate_bundles(bundles, tmp_path / "warehouse.duckdb")

    assert report["imported"] == ["duplicate", "second"]
    assert report["already_seen"] == ["first"]
    assert report["conflicts"] == 1
    assert report["warehouse_runs"] == 1
    assert report["unresolved_conflicts"] == 1


def test_collator_refuses_corrupt_file_without_importing(tmp_path) -> None:
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    path = bundles / "bad"
    _bundle(path, "original")
    (path / "runs.parquet").write_bytes(b"not parquet")

    report = collate_bundles(bundles, tmp_path / "warehouse.duckdb")

    assert report["imported"] == []
    assert report["refused"][0]["reason"] == "checksum mismatch for runs.parquet"
    assert report["warehouse_runs"] == 0
