"""Apply the decided rows of a ground-truth validation sheet to evaluation sets.

    python scripts/apply_validation.py --findings data/eval/validation/e2e_test_draft.csv \
        --set data/eval/e2e_test.v1.jsonl data/eval/e2e_v1.jsonl                 # dry run
    python scripts/apply_validation.py --findings ... --set ... --write          # rewrite the sets
    python scripts/apply_validation.py --fields data/eval/validation/gold_fields_draft.csv \
        --set data/eval/e2e_v1.jsonl data/eval/e2e_dev.v1.jsonl data/eval/e2e_test.v1.jsonl \
        data/eval/e2e_dev_extra.v1.jsonl --write
    python scripts/apply_validation.py --findings ... --set ... --validated-by T1 --write

Findings sheet (`data/eval/validation/<set>_<validator>.csv`): `id, field, gold, proposed, rule,
note, confidence, decision, decided_by`. `gold` and `proposed` hold JSON values. Only rows with
`decision = accept` change an item; `reject` rows are recorded as kept. A row whose `gold` no
longer matches the item is an error (the sheet is stale), never silently applied. Each changed
item gets `gold_version = 2` and one entry per change in `gold_changes` (field, old, new, rule,
decided_by).

Fields sheet (`gold_fields_draft.csv`): `id, domain, clarify_slot, clarify_options, rule,
decision, decided_by`; accepted rows set the three hand-filled fields.

`--validated-by` marks every item of the given sets `validated = true`, with that validator and
`gold_version = 2`. It refuses while any findings row for those items is undecided: an item is
validated only after a person has decided every proposed change to it. The same item in several
files (`e2e_v1.jsonl` and its split files) receives the same changes.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

DECISIONS = {"accept", "reject", ""}
HAND_FIELDS = ("domain", "clarify_slot", "clarify_options")


class ValidationError(ValueError):
    """A sheet that cannot be applied as it stands."""


def read_rows(path: Path) -> list[dict[str, str]]:
    """Rows of a sheet, without the `_summary` row."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if not row["id"].startswith("_")]
    for row in rows:
        decision = row.get("decision", "").strip().lower()
        if decision not in DECISIONS:
            msg = f"{path.name}: {row['id']}: decision must be accept, reject or empty"
            raise ValidationError(msg)
        if decision and not row.get("decided_by", "").strip():
            msg = f"{path.name}: {row['id']}: a decided row needs decided_by"
            raise ValidationError(msg)
        row["decision"] = decision
    return rows


def apply_findings(item: dict[str, Any], rows: list[dict[str, str]]) -> list[str]:
    """Apply the accepted findings rows of one item in place; return a log line per row."""
    log: list[str] = []
    for row in rows:
        field, old, new = row["field"], json.loads(row["gold"]), json.loads(row["proposed"])
        if row["decision"] != "accept":
            log.append(f"{item['id']} {field}: {row['decision'] or 'undecided'}")
            continue
        if item.get(field) != old:
            current = item.get(field)
            msg = f"{item['id']} {field}: sheet gold {old!r} differs from the item {current!r}"
            raise ValidationError(msg)
        if old == new:
            log.append(f"{item['id']} {field}: confirmed ({row['rule']})")
            continue
        item[field] = new
        item["gold_version"] = 2
        item.setdefault("gold_changes", []).append(
            {
                "field": field,
                "old": old,
                "new": new,
                "rule": row["rule"],
                "decided_by": row["decided_by"],
            }
        )
        log.append(f"{item['id']} {field}: changed ({row['rule']})")
    return log


def apply_fields(item: dict[str, Any], row: dict[str, str]) -> str:
    """Set the hand-filled gold fields of one item from an accepted fields row."""
    if row["decision"] != "accept":
        return f"{item['id']} fields: {row['decision'] or 'undecided'}"
    item["domain"] = row["domain"] or None
    item["clarify_slot"] = row["clarify_slot"] or None
    item["clarify_options"] = json.loads(row["clarify_options"]) if row["clarify_options"] else None
    return f"{item['id']} fields: set"


def apply(
    sets: dict[Path, list[dict[str, Any]]],
    findings: list[dict[str, str]],
    fields: list[dict[str, str]],
    validated_by: str | None,
) -> list[str]:
    """Apply findings, fields and the validated mark to every item of the sets (in place)."""
    by_id: dict[str, list[dict[str, str]]] = {}
    for row in findings:
        by_id.setdefault(row["id"], []).append(row)
    field_rows = {row["id"]: row for row in fields}
    known = {item["id"] for items in sets.values() for item in items}
    unknown = (set(by_id) | set(field_rows)) - known
    if unknown:
        msg = f"rows for items not in the given sets: {sorted(unknown)}"
        raise ValidationError(msg)
    if validated_by:
        open_rows = sorted({r["id"] for r in findings if r["id"] in known and not r["decision"]})
        if open_rows:
            msg = f"undecided rows remain for {open_rows}: decide them before --validated-by"
            raise ValidationError(msg)
    log: list[str] = []
    for path, items in sets.items():
        for item in items:
            lines = apply_findings(item, by_id.get(item["id"], []))
            if item["id"] in field_rows:
                lines.append(apply_fields(item, field_rows[item["id"]]))
            if validated_by:
                item["validated"] = True
                item["validated_by"] = validated_by
                item["gold_version"] = 2
            log.extend(f"{path.name}: {line}" for line in lines)
    return log


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--set", type=Path, nargs="+", required=True, help="JSONL sets")
    parser.add_argument("--findings", type=Path, nargs="*", default=[], help="findings sheets")
    parser.add_argument("--fields", type=Path, help="hand-filled gold fields sheet")
    parser.add_argument("--validated-by", help="mark every item validated by this member")
    parser.add_argument("--write", action="store_true", help="rewrite the sets in place")
    args = parser.parse_args(argv)

    sets = {
        path: [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        for path in args.set
    }
    findings = [row for sheet in args.findings for row in read_rows(sheet)]
    fields = read_rows(args.fields) if args.fields else []
    try:
        log = apply(sets, findings, fields, args.validated_by)
    except ValidationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for line in log:
        print(line)
    if args.write:
        for path, items in sets.items():
            text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
            path.write_text(text, encoding="utf-8")
            print(f"written: {path}")
    else:
        print("dry run: nothing written (use --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
