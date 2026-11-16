from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

def export_runs(db_path: Path, out_dir: Path, since: str | None = None) -> dict:
    """Export run-log tables to Parquet and create a checksum manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        counts, hashes = {}, {}
        for table in sorted(tables):
            query, params = f'SELECT * FROM "{table}"', ()
            if since and table == "runs":
                query, params = query + " WHERE started_at >= ?", (since,)
            frame = pd.read_sql_query(query, db, params=params)
            target = out_dir / f"{table}.parquet"
            frame.to_parquet(target, index=False)
            counts[table] = len(frame)
            hashes[table] = hashlib.sha256(target.read_bytes()).hexdigest()
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "unknown"
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "schema_version": 1,
                "git_sha": sha, "row_counts": counts, "sha256": hashes}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="outputs/runs/runs.sqlite")
    parser.add_argument("--since")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    export_runs(Path(args.db), Path(args.out), args.since)

if __name__ == "__main__":
    main()
