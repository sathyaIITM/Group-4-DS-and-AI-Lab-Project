"""Agreement, adjudication files and freeze for the dev_human routing set.

    # progress: which items each labeller still has to label
    python scripts/label_agreement.py status
    # Cohen's kappa per decision and block; writes disagreements_<adjudicator>.csv
    python scripts/label_agreement.py agree
    # after adjudication: the frozen set, its SHA-256 and the removed (ambiguous) items
    python scripts/label_agreement.py freeze --items data/labels/dev_human_v1/items_rendered.jsonl
    # diagnostic after the freeze only: final labels against T3's sealed intended labels
    python scripts/label_agreement.py compare --intended <path to intended_labels.csv>

Protocol: T3 brief Section 6. The target is kappa >= 0.80 per decision; below it the rule is
clarified and the disagreeing stratum is labelled again.
"""

import argparse
import json
import sys
from pathlib import Path

from analyst.evaluation import dev_human as dh

LABEL_DIR = Path("data/labels/dev_human_v1")
FROZEN = Path("data/splits/kev/dev_human.v1.jsonl")


def load_labels(directory: Path) -> dict:
    """Load every member's label file."""
    return {
        p.stem.removeprefix("labels_"): dh.read_labels(p)
        for p in sorted(directory.glob("labels_T*.csv"))
    }


def load_adjudications(directory: Path) -> list[dict[str, str]]:
    """Load the adjudication rows."""
    import csv

    rows: list[dict[str, str]] = []
    for path in sorted(directory.glob("disagreements_T*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def main() -> int:
    """Command-line entry point for label agreement."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--dir", type=Path, default=LABEL_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    agree = sub.add_parser("agree")
    agree.add_argument(
        "--overwrite", action="store_true", help="replace existing adjudication files"
    )
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--items", type=Path, required=True)
    freeze.add_argument("--out", type=Path, default=FROZEN)
    compare = sub.add_parser("compare")
    compare.add_argument("--intended", type=Path, required=True)
    compare.add_argument("--frozen", type=Path, default=FROZEN)
    args = parser.parse_args()

    labels = load_labels(args.dir)
    if args.command == "status":
        items = [r["id"] for r in dh.read_jsonl(args.dir / "items.jsonl")]
        for member, todo in dh.missing_items(labels, items).items():
            print(f"{member}: {len(todo)} items left" + (f" (first {todo[0]})" if todo else ""))
        return 0
    if args.command == "agree":
        result = dh.agreement(labels)
        (args.dir / "agreement.json").write_text(json.dumps(result, indent=2) + "\n")
        for adjudicator, rows in dh.disagreements(labels).items():
            path = args.dir / f"disagreements_{adjudicator}.csv"
            if path.exists() and not args.overwrite:
                print(f"kept {path} (already exists; --overwrite replaces it)")
                continue
            dh.write_csv(path, dh.DISAGREEMENT_COLUMNS, rows)
            print(f"wrote {path}: {len(rows)} rows")
        print(json.dumps(result["overall"], indent=2))
        print("meets target" if result["meets_target"] else "BELOW TARGET: clarify the rule")
        return 0
    if args.command == "freeze":
        items = dh.read_jsonl(args.items)
        final, ambiguous, unresolved = dh.final_labels(
            labels, load_adjudications(args.dir), [r["id"] for r in items]
        )
        if unresolved:
            print(f"not frozen: {len(unresolved)} items unresolved, e.g. {unresolved[:5]}")
            return 1
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as handle:
            for item in items:
                if item["id"] in final:
                    row = {**item, **final[item["id"]], "label_source": "human"}
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        card = {
            "file": str(args.out),
            "sha256": dh.sha256_file(args.out),
            "items_source": str(args.items),
            "items_source_sha256": dh.sha256_file(args.items),
            "kept": len(final),
            "removed_ambiguous": ambiguous,
        }
        (args.dir / "freeze.json").write_text(json.dumps(card, indent=2) + "\n")
        print(json.dumps(card, indent=2))
        return 0
    final = {r["id"]: {d: r[d] for d in dh.DECISIONS} for r in dh.read_jsonl(args.frozen)}
    print(json.dumps(dh.compare_intended(final, args.intended), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
