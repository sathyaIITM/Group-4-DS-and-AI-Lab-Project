"""Validate member run bundles and idempotently collate them into a DuckDB warehouse."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "runs": ("run_id",),
    "node_events": ("run_id", "seq"),
    "llm_calls": ("run_id", "seq"),
    "decisions": ("run_id", "seq"),
    "retrievals": ("run_id", "seq"),
    "sql_attempts": ("run_id", "seq"),
    "checks": ("run_id", "seq"),
    "artifacts": ("run_id",),
    "evidence": ("evidence_id",),
    "data_requests": ("run_id",),
}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_bundle(bundle: Path) -> tuple[dict[str, Any], str]:
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("manifest.json is missing")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    manifest_sha = hashlib.sha256(raw).hexdigest()
    if manifest.get("schema_version") != 1:
        raise ValueError(f"unknown schema_version: {manifest.get('schema_version')!r}")
    for field in ("member", "machine_id", "time_range", "row_counts", "sha256", "git_shas"):
        if field not in manifest:
            raise ValueError(f"manifest is missing {field}")
    if manifest["member"] not in {"T1", "T2", "T3", "T4"}:
        raise ValueError("manifest member must be T1, T2, T3 or T4")
    if not isinstance(manifest["time_range"], dict) or not isinstance(manifest["git_shas"], list):
        raise ValueError("manifest time_range or git_shas has the wrong type")
    counts, hashes = manifest["row_counts"], manifest["sha256"]
    for table in TABLE_KEYS:
        file_path = bundle / f"{table}.parquet"
        if not file_path.is_file():
            raise ValueError(f"{table}.parquet is missing")
        wanted_hash = hashes.get(table)
        if wanted_hash is None or _sha256(file_path) != wanted_hash:
            raise ValueError(f"checksum mismatch for {table}.parquet")
        if table not in counts or not isinstance(counts[table], int) or counts[table] < 0:
            raise ValueError(f"manifest row count is missing or invalid for {table}")
    return manifest, manifest_sha


def _ensure_warehouse(db: Any) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS bundles (
            manifest_sha256 VARCHAR PRIMARY KEY, member VARCHAR NOT NULL,
            machine_id VARCHAR NOT NULL, imported_at TIMESTAMP NOT NULL,
            row_counts_json VARCHAR NOT NULL, git_shas_json VARCHAR NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS collation_conflicts (
            manifest_sha256 VARCHAR NOT NULL, table_name VARCHAR NOT NULL,
            row_key VARCHAR NOT NULL, existing_row VARCHAR NOT NULL,
            incoming_row VARCHAR NOT NULL, found_at TIMESTAMP NOT NULL
        )"""
    )


def _columns(db: Any, table: str) -> list[str]:
    return [str(row[0]) for row in db.execute(f'DESCRIBE "{table}"').fetchall()]


def _read_parquet(db: Any, path: Path) -> tuple[list[str], list[tuple[Any, ...]]]:
    columns = [
        str(row[0])
        for row in db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
    ]
    rows = db.execute("SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
    return columns, rows


def _create_table(db: Any, table: str, path: Path, key_columns: tuple[str, ...]) -> list[str]:
    db.execute(
        f'CREATE TABLE "{table}" AS SELECT * FROM read_parquet(?) WHERE FALSE',  # noqa: S608 - table is allowlisted
        [str(path)],
    )
    columns = _columns(db, table)
    missing = set(key_columns) - set(columns)
    if missing:
        raise ValueError(f"{table} is missing key columns {sorted(missing)}")
    index_name = f"uidx_{table}_bundle_key"
    joined = ", ".join(f'"{column}"' for column in key_columns)
    db.execute(f'CREATE UNIQUE INDEX "{index_name}" ON "{table}" ({joined})')
    return columns


def _row_dict(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(columns, row, strict=True))


def _insert_table(
    db: Any,
    bundle: Path,
    manifest_sha: str,
    table: str,
    expected_count: int,
) -> tuple[int, int]:
    path = bundle / f"{table}.parquet"
    incoming_columns, rows = _read_parquet(db, path)
    if len(rows) != expected_count:
        raise ValueError(
            f"row count mismatch for {table}: manifest {expected_count}, file {len(rows)}"
        )
    if table not in _tables(db):
        columns = _create_table(db, table, path, TABLE_KEYS[table])
    else:
        columns = _columns(db, table)
        if columns != incoming_columns:
            raise ValueError(
                f"column schema mismatch for {table}; an explicit migration is required"
            )
    key_columns = TABLE_KEYS[table]
    key_indices = [incoming_columns.index(name) for name in key_columns]
    select_sql = f'SELECT * FROM "{table}" WHERE ' + " AND ".join(  # noqa: S608 - table and columns are allowlisted
        f'"{name}" = ?' for name in key_columns
    )
    insert_sql = (
        f'INSERT INTO "{table}" VALUES '  # noqa: S608 - table is allowlisted
        f"({', '.join('?' for _ in incoming_columns)}) ON CONFLICT DO NOTHING"
    )
    inserted = conflicts = 0
    for row in rows:
        key = tuple(row[index] for index in key_indices)
        existing = db.execute(select_sql, list(key)).fetchone()
        if existing is not None:
            if _json(_row_dict(columns, existing)) != _json(_row_dict(incoming_columns, row)):
                db.execute(
                    "INSERT INTO collation_conflicts VALUES (?,?,?,?,?,?)",
                    [
                        manifest_sha,
                        table,
                        _json(key),
                        _json(_row_dict(columns, existing)),
                        _json(_row_dict(incoming_columns, row)),
                        datetime.now(UTC),
                    ],
                )
                conflicts += 1
            continue
        db.execute(insert_sql, list(row))
        inserted += 1
    return inserted, conflicts


def _tables(db: Any) -> set[str]:
    return {str(row[0]) for row in db.execute("SHOW TABLES").fetchall()}


def collate_bundles(bundles_dir: Path, warehouse_path: Path) -> dict[str, Any]:
    """Import bundles once; refuse corrupt schemas and log row conflicts."""
    import duckdb

    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect(str(warehouse_path))
    _ensure_warehouse(db)
    report: dict[str, Any] = {
        "warehouse": str(warehouse_path),
        "imported": [],
        "already_seen": [],
        "refused": [],
        "rows_inserted": {},
        "conflicts": 0,
    }
    for bundle in sorted(path for path in bundles_dir.iterdir() if path.is_dir()):
        try:
            manifest, manifest_sha = _validate_bundle(bundle)
        except Exception as error:
            report["refused"].append({"bundle": bundle.name, "reason": str(error)})
            continue
        if db.execute("SELECT 1 FROM bundles WHERE manifest_sha256=?", [manifest_sha]).fetchone():
            report["already_seen"].append(bundle.name)
            continue
        db.execute("BEGIN TRANSACTION")
        try:
            inserted: dict[str, int] = {}
            bundle_conflicts = 0
            for table in TABLE_KEYS:
                count, conflicts = _insert_table(
                    db, bundle, manifest_sha, table, manifest["row_counts"][table]
                )
                inserted[table] = count
                bundle_conflicts += conflicts
            db.execute(
                "INSERT INTO bundles VALUES (?,?,?,?,?,?)",
                [
                    manifest_sha,
                    manifest["member"],
                    manifest["machine_id"],
                    datetime.now(UTC),
                    _json(manifest["row_counts"]),
                    _json(manifest["git_shas"]),
                ],
            )
            db.execute("COMMIT")
            report["imported"].append(bundle.name)
            report["rows_inserted"][bundle.name] = inserted
            report["conflicts"] += bundle_conflicts
        except Exception as error:
            db.execute("ROLLBACK")
            report["refused"].append({"bundle": bundle.name, "reason": str(error)})
    report["warehouse_runs"] = (
        db.execute("SELECT count(*) FROM runs").fetchone()[0] if "runs" in _tables(db) else 0
    )
    report["unresolved_conflicts"] = db.execute(
        "SELECT count(*) FROM collation_conflicts"
    ).fetchone()[0]
    db.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", type=Path, required=True)
    parser.add_argument("--warehouse", type=Path, default=Path("outputs/warehouse/runs.duckdb"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = collate_bundles(args.bundles, args.warehouse)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return int(bool(result["refused"]))


if __name__ == "__main__":
    raise SystemExit(main())
