from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

BUNDLE_TABLES = (
    "runs",
    "node_events",
    "llm_calls",
    "decisions",
    "retrievals",
    "sql_attempts",
    "checks",
    "artifacts",
    "evidence",
    "data_requests",
)


def export_runs(
    db_path: Path, out_dir: Path, since: str | None = None, member: str | None = None
) -> dict:
    """Export a reproducible, incremental bundle with a manifest for the T4 collator."""
    member = member or os.environ.get("TEAM_MEMBER")
    if member not in {"T1", "T2", "T3", "T4"}:
        raise ValueError("pass --member T1..T4 or set TEAM_MEMBER")
    out_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS export_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        previous = db.execute(
            "SELECT value FROM export_meta WHERE key='last_exported_started_at'"
        ).fetchone()
        effective_since = since or (previous[0] if previous else None)
        time_operator = ">=" if since is not None else ">"
        existing = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = sorted(set(BUNDLE_TABLES) - existing)
        if missing:
            raise ValueError(f"run log database is missing tables: {missing}")
        run_query = "SELECT run_id, started_at, ended_at, git_sha FROM runs"
        run_params: tuple[str, ...] = ()
        if effective_since:
            run_query += f" WHERE started_at {time_operator} ?"
            run_params = (effective_since,)
        selected_runs = pd.read_sql_query(run_query, db, params=run_params)
        run_ids = selected_runs["run_id"].astype(str).tolist()
        counts: dict[str, int] = {}
        hashes: dict[str, str] = {}
        for table in BUNDLE_TABLES:
            query = f'SELECT * FROM "{table}"'  # noqa: S608 - fixed allowlisted table names
            params: tuple[str, ...] = ()
            if table == "runs" and effective_since:
                query += f" WHERE started_at {time_operator} ?"
                params = (effective_since,)
            elif table != "runs" and "run_id" in [
                column[1] for column in db.execute(f'PRAGMA table_info("{table}")')
            ]:
                if run_ids:
                    query += " WHERE run_id IN (" + ",".join("?" for _ in run_ids) + ")"
                    params = tuple(run_ids)
                elif effective_since:
                    query += " WHERE 1=0"
            frame = pd.read_sql_query(query, db, params=params)
            target = out_dir / f"{table}.parquet"
            frame.to_parquet(target, index=False)
            counts[table] = len(frame)
            hashes[table] = hashlib.sha256(target.read_bytes()).hexdigest()
        if not selected_runs.empty:
            latest = str(selected_runs["started_at"].astype(str).max())
            db.execute(
                "INSERT INTO export_meta VALUES ('last_exported_started_at', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (latest,),
            )
    time_range = {
        "started_at_min": str(selected_runs["started_at"].min())
        if not selected_runs.empty
        else None,
        "started_at_max": str(selected_runs["started_at"].max())
        if not selected_runs.empty
        else None,
        "ended_at_max": str(selected_runs["ended_at"].max()) if not selected_runs.empty else None,
    }
    machine_id = hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()[:12]
    manifest = {
        "member": member,
        "machine_id": machine_id,
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": 1,
        "time_range": time_range,
        "git_shas": sorted(set(selected_runs["git_sha"].dropna().astype(str)))
        if not selected_runs.empty
        else [],
        "row_counts": counts,
        "sha256": hashes,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="outputs/runs/runs.sqlite")
    parser.add_argument("--since")
    parser.add_argument("--out", required=True)
    parser.add_argument("--member", choices=["T1", "T2", "T3", "T4"])
    args = parser.parse_args()
    export_runs(Path(args.db), Path(args.out), args.since, args.member)


if __name__ == "__main__":
    main()
