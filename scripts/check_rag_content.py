"""Check the RAG content: guidance cards and verified examples (T1 brief, Section 5.2).

    python scripts/check_rag_content.py
    python scripts/check_rag_content.py --out outputs/reports/rag_content_check_v1.json

Cards: unique ids, required fields, a known `dataset_id` (or null for an analysis SOP) and a
body of at most 60 words. Examples: unique ids, required fields, a known `dataset_id`, SQL that
reads `obs_<dataset_id>` and passes the agent's read-only guard (tools/sql_runner.py), and a
result whose row count equals `expected_rows`. Example questions are compared with every
evaluation question (data/ground_truths/*.csv, and data/eval/e2e_v1.jsonl and
data/labels/dev_human_v1/items.jsonl when present) by character 5-gram Jaccard; a similarity at
or above the threshold is flagged, because retrieval must not hand the agent an evaluation
answer.

Exit code 1 when any check fails or any example is flagged. Run from the repository root after
the pipeline has published every table; `--processed` points at another published release.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from analyst.evaluation.dev_human import OVERLAP_THRESHOLD, messages_of, overlap, read_jsonl
from analyst.tools.sql_runner import ReadOnlyDatabase

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
EVAL_SET = ROOT / "data" / "eval" / "e2e_v1.jsonl"
DEV_HUMAN = ROOT / "data" / "labels" / "dev_human_v1" / "items.jsonl"
CARDS = ROOT / "configs" / "rag" / "guidance_cards.v3.json"
EXAMPLES = ROOT / "data" / "sample" / "rag_verified_examples.v2.jsonl"
MAX_WORDS = 60
CARD_FIELDS = {"id", "dataset_id", "kind", "title", "body"}
CARD_KINDS = {"convention", "analysis_sop"}
EXAMPLE_FIELDS = {
    "id",
    "dataset_id",
    "question",
    "sql",
    "expected_rows",
    "verified_by",
    "verified_on",
}


def check_cards(cards: list[dict[str, Any]], datasets: set[str]) -> list[str]:
    """Return problems with the guidance cards."""
    problems = []
    seen: set[str] = set()
    for card in cards:
        cid = str(card.get("id"))
        if missing := CARD_FIELDS - card.keys():
            problems.append(f"card {cid}: missing {sorted(missing)}")
        if cid in seen:
            problems.append(f"card {cid}: duplicate id")
        seen.add(cid)
        if card.get("kind") not in CARD_KINDS:
            problems.append(f"card {cid}: kind {card.get('kind')!r}")
        dataset = card.get("dataset_id")
        if dataset is None and card.get("kind") != "analysis_sop":
            problems.append(f"card {cid}: dataset_id is null but kind is not analysis_sop")
        if dataset is not None and dataset not in datasets:
            problems.append(f"card {cid}: unknown dataset_id {dataset}")
        words = len(str(card.get("body", "")).split())
        if words > MAX_WORDS:
            problems.append(f"card {cid}: body has {words} words (max {MAX_WORDS})")
    return problems


def check_examples(
    examples: list[dict[str, Any]], datasets: set[str], db: ReadOnlyDatabase
) -> tuple[list[str], list[dict[str, Any]]]:
    """Run the verified examples and return their problems and results."""
    problems = []
    results = []
    seen: set[str] = set()
    for example in examples:
        eid = str(example.get("id"))
        if missing := EXAMPLE_FIELDS - example.keys():
            problems.append(f"example {eid}: missing {sorted(missing)}")
        if eid in seen:
            problems.append(f"example {eid}: duplicate id")
        seen.add(eid)
        dataset = str(example.get("dataset_id"))
        if dataset not in datasets:
            problems.append(f"example {eid}: unknown dataset_id {dataset}")
        if f"obs_{dataset}" not in str(example.get("sql", "")):
            problems.append(f"example {eid}: SQL does not read obs_{dataset}")
        try:
            columns, rows = db.run(str(example.get("sql", "")))
        except Exception as error:  # report every failing example, not only the first
            problems.append(f"example {eid}: {type(error).__name__}: {error}")
            continue
        if len(rows) != example.get("expected_rows"):
            problems.append(
                f"example {eid}: {len(rows)} rows, expected_rows {example.get('expected_rows')}"
            )
        results.append(
            {
                "id": eid,
                "rows": len(rows),
                "columns": columns,
                "first_row": list(rows[0]) if rows else None,
            }
        )
    return problems, results


def evaluation_questions() -> dict[str, list[str]]:
    """Return the evaluation questions per source file, to detect leakage."""
    sources: dict[str, list[str]] = {}
    for path in sorted((ROOT / "data" / "ground_truths").glob("*.csv")):
        with path.open(encoding="utf-8") as handle:
            sources[path.name] = [row["question"] for row in csv.DictReader(handle)]
    for path in (EVAL_SET, DEV_HUMAN):
        if path.exists():
            sources[path.name] = messages_of(path)
    return sources


def main() -> int:
    """Check the guidance cards and verified examples."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--cards", type=Path, default=CARDS)
    parser.add_argument("--examples", type=Path, default=EXAMPLES)
    parser.add_argument("--threshold", type=float, default=OVERLAP_THRESHOLD)
    parser.add_argument("--processed", type=Path, default=PROCESSED)
    parser.add_argument("--reference", type=Path, nargs="*", default=[])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    processed: Path = args.processed
    catalogue = json.loads((processed / "catalogue.json").read_text(encoding="utf-8"))
    datasets = {t["dataset_id"] for t in catalogue["tables"]}
    db = ReadOnlyDatabase({f"obs_{d}": processed / f"obs_{d}.parquet" for d in sorted(datasets)})

    cards = json.loads(args.cards.read_text(encoding="utf-8"))["cards"]
    examples = read_jsonl(args.examples)
    problems = check_cards(cards, datasets)
    example_problems, results = check_examples(examples, datasets, db)
    problems += example_problems
    references = evaluation_questions()
    for path in args.reference:
        references[str(path)] = messages_of(path)
    leak = overlap(
        [{"id": e["id"], "message": e["question"]} for e in examples], references, args.threshold
    )

    covered = {c["dataset_id"] for c in cards if c["dataset_id"]}
    report = {
        "cards": len(cards),
        "examples": len(examples),
        "catalogue_tables": sorted(datasets),
        "tables_without_card": sorted(datasets - covered),
        "tables_without_example": sorted(datasets - {e["dataset_id"] for e in examples}),
        "dataset_versions": {t["dataset_id"]: t["dataset_version"] for t in catalogue["tables"]},
        "problems": problems,
        "evaluation_overlap": leak,
        "example_results": results,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    summary = {
        k: report[k]
        for k in ("cards", "examples", "tables_without_card", "tables_without_example", "problems")
    }
    summary["flagged"] = leak["flagged"]
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if problems or leak["flagged"] else 0


if __name__ == "__main__":
    sys.exit(main())
