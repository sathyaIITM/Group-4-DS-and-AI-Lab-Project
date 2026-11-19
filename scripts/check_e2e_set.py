"""Validate the end-to-end evaluation set (e2e_v1): shape, quotas, and gold SQL results.

    python scripts/check_e2e_set.py
    python scripts/check_e2e_set.py --set data/eval/e2e_v1.jsonl \
        --out outputs/reports/e2e_v1_check.json

Checks, in order:
1. every line is a JSON object with the fields of the specification, correctly typed, with unique
   ids and questions;
2. action rules: `answer` items carry gold SQL and expected values; `decline` items have no
   dataset ids; `clarify` items name the missing slot in `notes`; `describe` and `search` items
   carry no SQL;
3. the gold SQL of every item runs through the read-only guard (`ReadOnlyDatabase`), reads only
   the item's own `obs_<dataset>` tables, and its result equals `expected_values` within
   `tolerance` (relative). The values are the non-null cells of the `value` column, in row order.
   When `derivation` is set (difference, pct_change or share_pct) the expected value is derived
   from those cells in Python, never in SQL;
4. every `expected_entities` name appears in the `entity` column of the result;
5. quotas of the T1 brief, Section 6: action mix, 5 to 20 questions per published table, the seven
   operations, at least 10 derived values, 15 items testing one of the named conventions
   (`SPEC_CONVENTIONS`; other tags are descriptive only), 10 follow-ups.

The report (counts by action, table, operation and convention, plus every error) is written to
`--out`. Exit code 1 when any error is found. Requires the published tables
(`data/processed/obs_*.parquet`, git-ignored).
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from analyst.tools.sql_runner import ReadOnlyDatabase

ACTIONS = ("answer", "decline", "clarify", "describe", "search")
OPERATIONS = ("lookup", "ranking", "change", "trend", "comparison", "aggregate", "share")
REQUIRED_CONVENTIONS = (
    "survey_year",
    "monsoon_season",
    "subdivision_mapping",
    "orissa_spelling",
    "total_row",
    "suppressed_value",
    "index_vs_rate",
)
DERIVATIONS = ("difference", "pct_change", "share_pct")
# Ids above this are the dev supplement (data/eval/e2e_dev_extra.v1.jsonl, 19 Nov), written by T3
# from the catalogue and the design rules to cover describe, search, clarify, decline and
# multi-turn items that e2e_dev lacks; e2e_v1 and its test split are unchanged.
SUPPLEMENT_FROM = 100
# Convention classes named in the brief: survey year, monsoon season, sub-division mapping,
# Orissa, total row, suppressed value, index versus rate (with their close variants).
SPEC_CONVENTIONS = frozenset(
    {
        "survey_year",
        "crop_year",
        "fiscal_year",
        "calendar_vs_survey_year",
        "monsoon_season",
        "subdivision_mapping",
        "composite_subdivision",
        "orissa_spelling",
        "total_row",
        "suppressed_value",
        "low_sample",
        "index_vs_rate",
        "rate_vs_count",
    }
)
MIN_ANSWER, MIN_DECLINE, MIN_CLARIFY, MIN_DESCRIBE_SEARCH = 70, 12, 8, 3
MIN_PER_TABLE, MAX_PER_TABLE = 5, 20
MIN_DERIVED, MIN_CONVENTION_ITEMS, MIN_FOLLOW_UPS = 10, 15, 10
TOTAL_ITEMS = 100
ABS_FLOOR = 1e-6

FIELDS: dict[str, type | tuple[type, ...]] = {
    "id": str,
    "question": str,
    "prior_turns": list,
    "expected_action": str,
    "dataset_ids": list,
    "gold_sql": (str, type(None)),
    "expected_values": list,
    "expected_entities": list,
    "tolerance": (int, float),
    "expected_caveats": list,
    "operation": str,
    "derivation": (str, type(None)),
    "conventions": list,
    "notes": str,
    "author": str,
    "validated": bool,
    "written_on": str,
}


def derive(kind: str, values: list[float]) -> list[float]:
    """Derived expected value from the gold rows (see the module docstring)."""
    if kind == "difference":
        return [round(values[-1] - values[0], 4)]
    if kind == "pct_change":
        return [round((values[-1] - values[0]) / values[0] * 100, 2)]
    if kind == "share_pct":
        return [round(values[0] / values[1] * 100, 2)]
    msg = f"unknown derivation: {kind}"
    raise ValueError(msg)


def close(actual: float, expected: float, tolerance: float) -> bool:
    """Relative comparison with a tiny absolute floor for values near zero."""
    return abs(actual - expected) <= max(tolerance * abs(expected), ABS_FLOOR)


def read_items(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Load evaluation items, with errors for lines that are not valid JSON."""
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"line {number}: invalid JSON ({error})")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {number}: not a JSON object")
            continue
        items.append(row)
    return items, errors


def check_shape(item: dict[str, Any]) -> list[str]:
    """Return field-type problems of an item."""
    errors: list[str] = []
    for name, kind in FIELDS.items():
        if name not in item:
            errors.append(f"missing field {name}")
        elif not isinstance(item[name], kind) or (
            isinstance(item[name], bool) and name != "validated"
        ):
            errors.append(f"field {name} has the wrong type")
    extra = set(item) - set(FIELDS)
    if extra:
        errors.append(f"unknown fields {sorted(extra)}")
    if errors:
        return errors
    if not re.fullmatch(r"e2e-\d{3}", item["id"]):
        errors.append("id must look like e2e-001")
    if item["expected_action"] not in ACTIONS:
        errors.append(f"expected_action must be one of {ACTIONS}")
    supplement = (
        int(item["id"][4:]) > SUPPLEMENT_FROM if re.fullmatch(r"e2e-\d{3}", item["id"]) else False
    )
    if item["author"] != "T1" and not (supplement and item["author"] == "T3"):
        errors.append("author must be T1 (T3 only for dev-supplement ids above e2e-100)")
    try:
        date.fromisoformat(item["written_on"])
    except ValueError:
        errors.append("written_on must be an ISO date")
    if not 0 <= item["tolerance"] <= 1:
        errors.append("tolerance must be in [0, 1]")
    if item["derivation"] is not None and item["derivation"] not in DERIVATIONS:
        errors.append(f"derivation must be null or one of {DERIVATIONS}")
    for name in ("prior_turns", "dataset_ids", "expected_caveats", "conventions"):
        if not all(isinstance(x, str) for x in item[name]):
            errors.append(f"{name} must be a list of strings")
    if not all(isinstance(x, int | float) for x in item["expected_values"]):
        errors.append("expected_values must be numbers")
    return errors


def check_action_rules(item: dict[str, Any]) -> list[str]:
    """Return problems with the fields an item's expected action requires."""
    errors: list[str] = []
    action = item["expected_action"]
    if action == "answer":
        if not item["gold_sql"]:
            errors.append("answer item needs gold_sql")
        no_figure = {"missing_value", "suppressed_value"} & set(item.get("conventions", []))
        if not item["expected_values"] and not no_figure:
            # A value missing or suppressed in the source is answered by saying so, without a
            # figure (design Section 4.5); only those items may have no expected values.
            errors.append("answer item needs expected_values")
        if not item["dataset_ids"]:
            errors.append("answer item needs dataset_ids")
        if item["operation"] not in OPERATIONS:
            errors.append(f"operation must be one of {OPERATIONS}")
    else:
        if item["gold_sql"] is not None:
            errors.append(f"{action} item must not have gold_sql")
        if item["expected_values"]:
            errors.append(f"{action} item must not have expected_values")
        if item["derivation"] is not None:
            errors.append(f"{action} item must not have a derivation")
        if item["operation"] != action:
            errors.append(f"operation of a {action} item must be {action!r}")
    if action == "decline" and item["dataset_ids"]:
        errors.append("decline item must have empty dataset_ids")
    if action in ("clarify", "decline", "describe", "search") and not item["notes"].strip():
        errors.append(f"{action} item needs notes (missing slot, reason or expected content)")
    if action in ("clarify", "describe") and not item["dataset_ids"]:
        errors.append(f"{action} item needs dataset_ids")
    return errors


def tables_read(sql: str) -> set[str]:
    """Return the tables an SQL statement reads, excluding CTE names."""
    tree = sqlglot.parse_one(sql, read="duckdb")
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    return {t.name.lower() for t in tree.find_all(exp.Table)} - cte_names


def check_gold(item: dict[str, Any], database: ReadOnlyDatabase) -> list[str]:
    """Execute the gold SQL and compare with the expected values and entities."""
    sql = item["gold_sql"]
    errors: list[str] = []
    allowed = {f"obs_{name}" for name in item["dataset_ids"]}
    stray = tables_read(sql) - allowed
    if stray:
        errors.append(f"gold_sql reads tables outside dataset_ids: {sorted(stray)}")
    try:
        columns, rows = database.run(sql)
    except Exception as error:
        return [*errors, f"gold_sql failed: {error}"]
    records = [dict(zip(columns, row, strict=True)) for row in rows]
    if "value" not in columns:
        return [*errors, "gold_sql must return a column named value"]
    cells = [float(r["value"]) for r in records if r["value"] is not None]
    if item["derivation"]:
        minimum = 2
        if len(cells) < minimum:
            return [*errors, f"derivation {item['derivation']} needs at least two value cells"]
        if item["derivation"] == "share_pct" and len(cells) != minimum:
            errors.append("share_pct needs exactly two value cells (part, then whole)")
        cells = derive(item["derivation"], cells)
    expected = [float(v) for v in item["expected_values"]]
    if len(cells) != len(expected):
        errors.append(f"expected {len(expected)} values, gold result has {len(cells)}: {cells}")
    else:
        for position, (actual, wanted) in enumerate(zip(cells, expected, strict=True)):
            if not close(actual, wanted, item["tolerance"]):
                errors.append(f"value {position}: gold {actual} differs from expected {wanted}")
    if item["expected_entities"]:
        if "entity" not in columns:
            errors.append("expected_entities given but gold_sql has no entity column")
        else:
            found = {str(r["entity"]).lower() for r in records}
            missing = [e for e in item["expected_entities"] if str(e).lower() not in found]
            if missing:
                errors.append(f"entities not in the gold result: {missing}")
    return errors


def published_tables(processed: Path) -> list[str]:
    """Return the dataset ids with a published observation table."""
    return sorted(p.stem[len("obs_") :] for p in processed.glob("obs_*.parquet"))


def summarise(items: list[dict[str, Any]], tables: list[str]) -> dict[str, Any]:
    """Count items by action, table and operation."""
    by_action = Counter(i["expected_action"] for i in items)
    by_table = Counter(name for i in items for name in set(i["dataset_ids"]))
    by_operation = Counter(i["operation"] for i in items if i["expected_action"] == "answer")
    by_convention = Counter(c for i in items for c in set(i["conventions"]))
    return {
        "items": len(items),
        "by_action": dict(sorted(by_action.items())),
        "by_table": {t: by_table.get(t, 0) for t in tables},
        "by_operation": dict(sorted(by_operation.items())),
        "by_convention": dict(sorted(by_convention.items())),
        "derived_values": sum(1 for i in items if i["derivation"]),
        "items_with_convention": sum(1 for i in items if SPEC_CONVENTIONS & set(i["conventions"])),
        "follow_ups": sum(1 for i in items if i["prior_turns"]),
        "validated": sum(1 for i in items if i["validated"]),
    }


def check_quotas(summary: dict[str, Any], tables: list[str]) -> list[str]:
    """Return quota violations of the set."""
    errors: list[str] = []
    actions = summary["by_action"]
    minimums = {"answer": MIN_ANSWER, "decline": MIN_DECLINE, "clarify": MIN_CLARIFY}
    for action, minimum in minimums.items():
        if actions.get(action, 0) < minimum:
            errors.append(
                f"quota: at least {minimum} {action} items, found {actions.get(action, 0)}"
            )
    describe_search = actions.get("describe", 0) + actions.get("search", 0)
    if describe_search < MIN_DESCRIBE_SEARCH:
        errors.append(f"quota: at least {MIN_DESCRIBE_SEARCH} describe or search items")
    if summary["items"] != TOTAL_ITEMS:
        errors.append(f"quota: {TOTAL_ITEMS} items required, found {summary['items']}")
    for table in tables:
        count = summary["by_table"][table]
        if not MIN_PER_TABLE <= count <= MAX_PER_TABLE:
            errors.append(f"quota: {table} has {count} items, need {MIN_PER_TABLE}-{MAX_PER_TABLE}")
    for operation in OPERATIONS:
        if summary["by_operation"].get(operation, 0) == 0:
            errors.append(f"quota: no answer item with operation {operation}")
    for convention in REQUIRED_CONVENTIONS:
        if summary["by_convention"].get(convention, 0) == 0:
            errors.append(f"quota: no item tests convention {convention}")
    thresholds: list[tuple[str, int, int]] = [
        ("derived_values", summary["derived_values"], MIN_DERIVED),
        ("items_with_convention", summary["items_with_convention"], MIN_CONVENTION_ITEMS),
        ("follow_ups", summary["follow_ups"], MIN_FOLLOW_UPS),
    ]
    for name, found, minimum in thresholds:
        if found < minimum:
            errors.append(f"quota: {name} is {found}, at least {minimum} required")
    return errors


def unknown_datasets(items: list[dict[str, Any]], tables: list[str]) -> list[str]:
    """Return items that name an unpublished dataset."""
    known = set(tables)
    return [
        f"{i['id']}: unknown dataset id {name}"
        for i in items
        for name in i["dataset_ids"]
        if name not in known
    ]


def run(set_path: Path, processed: Path) -> dict[str, Any]:
    """Check an evaluation set and return the report."""
    items, errors = read_items(set_path)
    tables = published_tables(processed)
    shape_ok: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_questions: set[tuple[str, tuple[str, ...]]] = set()
    for item in items:
        label = str(item.get("id", "?"))
        problems = check_shape(item)
        if not problems:
            if item["id"] in seen_ids:
                problems.append("duplicate id")
            key = (item["question"].strip().lower(), tuple(item["prior_turns"]))
            if key in seen_questions:
                problems.append("duplicate question with identical prior turns")
            seen_ids.add(item["id"])
            seen_questions.add(key)
            problems += check_action_rules(item)
        errors += [f"{label}: {p}" for p in problems]
        if not problems:
            shape_ok.append(item)
    errors += unknown_datasets(shape_ok, tables)
    database = ReadOnlyDatabase({f"obs_{t}": processed / f"obs_{t}.parquet" for t in tables})
    for item in shape_ok:
        if item["expected_action"] == "answer":
            errors += [f"{item['id']}: {p}" for p in check_gold(item, database)]
    summary = summarise(shape_ok, tables)
    errors += check_quotas(summary, tables)
    return {"set": str(set_path), "tables": tables, "summary": summary, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for the evaluation-set check."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--set", type=Path, default=Path("data/eval/e2e_v1.jsonl"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--out", type=Path, default=Path("outputs/reports/e2e_v1_check.json"))
    args = parser.parse_args(argv)
    report = run(args.set, args.processed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(f"{summary['items']} items; actions {summary['by_action']}")
    print(f"tables {summary['by_table']}")
    print(f"operations {summary['by_operation']}")
    print(
        f"derived {summary['derived_values']}, "
        f"convention items {summary['items_with_convention']}, "
        f"follow-ups {summary['follow_ups']}, validated {summary['validated']}"
    )
    for error in report["errors"]:
        print(f"  ERROR {error}")
    print(f"{len(report['errors'])} errors; report written to {args.out}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
