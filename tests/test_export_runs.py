from __future__ import annotations

import json
import sqlite3

from analyst.ops.export_runs import BUNDLE_TABLES, export_runs


def _database(path) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE runs (run_id TEXT, started_at TEXT, ended_at TEXT, "
            "git_sha TEXT, question_id TEXT)"
        )
        db.executemany(
            "INSERT INTO runs VALUES (?,?,?,?,?)",
            [
                ("r1", "2026-11-17T10:00:00+00:00", "2026-11-17T10:00:02+00:00", "sha1", "q1"),
                ("r2", "2026-11-17T11:00:00+00:00", "2026-11-17T11:00:02+00:00", "sha2", "q2"),
            ],
        )
        for table in BUNDLE_TABLES:
            if table == "runs":
                continue
            if table == "evidence":
                db.execute(f"CREATE TABLE {table} (evidence_id TEXT, run_id TEXT, content TEXT)")
                db.executemany(
                    f"INSERT INTO {table} VALUES (?,?,?)", [("ev1", "r1", "a"), ("ev2", "r2", "b")]
                )
            elif table == "artifacts":
                db.execute(f"CREATE TABLE {table} (run_id TEXT, content TEXT)")
                db.executemany(f"INSERT INTO {table} VALUES (?,?)", [("r1", "a"), ("r2", "b")])
            else:
                db.execute(f"CREATE TABLE {table} (run_id TEXT, seq INTEGER, content TEXT)")
                db.executemany(
                    f"INSERT INTO {table} VALUES (?,?,?)", [("r1", 1, "a"), ("r2", 1, "b")]
                )


def test_export_manifest_and_incremental_child_filtering(tmp_path) -> None:
    database = tmp_path / "runs.sqlite"
    _database(database)
    first = export_runs(database, tmp_path / "bundle1", member="T4")
    second = export_runs(database, tmp_path / "bundle2", member="T4")

    assert first["member"] == "T4"
    assert len(first["sha256"]) == len(BUNDLE_TABLES)
    assert first["git_shas"] == ["sha1", "sha2"]
    assert first["row_counts"]["node_events"] == 2
    assert second["row_counts"]["runs"] == 0
    assert second["row_counts"]["node_events"] == 0
    assert json.loads((tmp_path / "bundle1" / "manifest.json").read_text())["machine_id"]
