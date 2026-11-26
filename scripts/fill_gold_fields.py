"""Fill the structured gold fields of an evaluation set from each item's gold SQL.

    python scripts/fill_gold_fields.py --set data/eval/e2e_v1.jsonl            # dry run
    python scripts/fill_gold_fields.py --set data/eval/e2e_v1.jsonl --write    # rewrite in place

Fields filled from the gold query: `expected_places`, `expected_periods`, `indicator_ids`, `unit`,
`n_values` (see `analyst.evaluation.gold_fields`). Fields filled by hand (`domain`,
`clarify_slot`, `clarify_options`) are added as `null` placeholders when absent and never changed.
A field that already holds a different value is kept and reported, unless `--overwrite` is given.

The dry run prints one line per item (tracing mode, places, periods, n_values) and every
difference or problem; `--report` also writes them as JSON. Requires the published tables
(`data/processed/obs_*.parquet`, git-ignored).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from analyst.evaluation.gold_fields import compute_fields, merge_fields
from analyst.tools.sql_runner import ReadOnlyDatabase


def open_database(processed: Path) -> ReadOnlyDatabase:
    """Load every published observation table into a read-only database."""
    tables = sorted(processed.glob("obs_*.parquet"))
    if not tables:
        msg = f"no obs_*.parquet tables in {processed}"
        raise SystemExit(msg)
    return ReadOnlyDatabase({path.stem: path for path in tables})


def fill(
    items: list[dict[str, Any]], database: ReadOnlyDatabase, overwrite: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the filled items and one report row per item."""
    filled: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    for item in items:
        try:
            computed = compute_fields(item, database)
        except Exception as error:  # a broken gold query is reported, not fatal
            filled.append(item)
            report.append({"id": item.get("id"), "mode": "error", "problems": [str(error)]})
            continue
        merged, differences = merge_fields(item, computed, overwrite=overwrite)
        filled.append(merged)
        report.append(
            {
                "id": computed.item_id,
                "mode": computed.mode,
                "fields": computed.fields,
                "differences": differences,
                "problems": computed.problems,
            }
        )
    return filled, report


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--set", type=Path, required=True, help="JSONL evaluation set")
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--write", action="store_true", help="rewrite the set in place")
    parser.add_argument("--overwrite", action="store_true", help="replace differing values")
    parser.add_argument("--report", type=Path, help="write the per-item report as JSON")
    args = parser.parse_args(argv)

    lines = args.set.read_text(encoding="utf-8").splitlines()
    items = [json.loads(line) for line in lines if line.strip()]
    database = open_database(args.processed)
    try:
        filled, report = fill(items, database, args.overwrite)
    finally:
        database.close()

    issues = 0
    for row in report:
        fields = row.get("fields", {})
        places = ", ".join(p["name"] for p in fields.get("expected_places", []))
        print(
            f"{row['id']}: {row['mode']}; n_values {fields.get('n_values')}; "
            f"periods {len(fields.get('expected_periods', []))}; places {places[:80]}"
        )
        for line in row.get("differences", []) + row.get("problems", []):
            issues += 1
            print(f"  ! {line}")
    print(f"{len(items)} items; {issues} differences or problems")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
        )
    if args.write:
        text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in filled)
        args.set.write_text(text, encoding="utf-8")
        print(f"written: {args.set}")
    else:
        print("dry run: nothing written (use --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
