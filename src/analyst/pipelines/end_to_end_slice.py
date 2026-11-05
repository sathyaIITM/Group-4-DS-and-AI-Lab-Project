"""End-to-end slice: a small run over the five published tables.

Each case passes through the stages below. The decision model and the SQL guard are the real
components. The query itself is replayed from the reference SQL because no hosted LLM is
connected yet; every output says so (`sql_source`). The slice therefore demonstrates the data
path, the guard, the checks and the evidence bundle, and it does not measure query generation.

    1. state     the catalogue lines of the five tables, the context line and the question
    2. domain    one choice question to a served Kev checkpoint
    3. ranking   tables of the predicted domain first; no table is removed
    4. SQL       reference SQL (stand-in), validated and run read-only in DuckDB
    5. checks    executed, non-empty, not truncated, quality flags counted, stored answer matched
    6. bundle    source, query, routing, checks and timing, and a templated answer

    python -m analyst.pipelines.end_to_end_slice --out outputs/predictions/end_to_end_slice.jsonl
"""

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analyst.decisions.kev_questions import STATE_CHAR_LIMIT, render_context
from analyst.decisions.phase1 import domain_question
from analyst.decisions.system_one import ChoiceQuestion, SystemOneClient
from analyst.tools.sql_runner import MAX_ROWS, ReadOnlyDatabase, SqlRejectedError, SqlTimeoutError

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"
SQL_SOURCE = "reference SQL replayed (stand-in for the hosted LLM)"
DATASET_NAMES = {
    "NFHS-5": "nfhs5_district_indicators",
    "Mandi": "mandi_daily_prices",
    "NCRB": "ncrb_annual_crime_statistics",
}


@dataclass(frozen=True)
class Case:
    case_id: str
    question: str
    sql: str
    dataset: str
    reference_answer: float | None = None


def load_catalogue(path: Path = PROCESSED / "catalogue.json") -> list[dict[str, Any]]:
    return list(json.loads(path.read_text(encoding="utf-8"))["tables"])


def catalogue_text(tables: list[dict[str, Any]]) -> str:
    """The catalogue field of the router state: one line per table."""
    return "\n".join(f"{i}. {t['dataset_id']}: {t['title']}" for i, t in enumerate(tables, 1))


def rank_tables(tables: list[dict[str, Any]], domain: str) -> list[dict[str, Any]]:
    """Tables of the predicted domain first. A ranking only: no table is removed."""
    if domain in {"multiple", "unspecified"}:
        return list(tables)
    return sorted(tables, key=lambda t: t["domain"] != domain)  # stable sort keeps the order


def load_cases(per_source: dict[str, int]) -> list[Case]:
    """Answerable cases: v0 questions (IMD, PLFS) and reference pairs (NFHS-5, Mandi, NCRB)."""
    cases: list[Case] = []
    v0 = [json.loads(line) for line in (ROOT / "data/sample/v0_questions.jsonl").open()]
    for table, n in (
        ("imd_subdivision_monthly_rainfall", per_source.get("IMD", 0)),
        ("plfs_state_ur_usual_status", per_source.get("PLFS", 0)),
    ):
        picked = [q for q in v0 if q["answerable"] and q["tables"] == [table]][:n]
        cases += [
            Case(
                q["id"],
                q["question"],
                q["reference_sql"],
                table,
                q.get("reference_answer")
                if isinstance(q.get("reference_answer"), int | float)
                else None,
            )
            for q in picked
        ]
    with (ROOT / "data/ground_truths/text_to_sql_dev.v1.csv").open(encoding="utf-8") as handle:
        pairs = [r for r in csv.DictReader(handle) if r["expected_action"] == "answer"]
    for source, name in DATASET_NAMES.items():
        picked = [r for r in pairs if r["dataset"] == source][: per_source.get(source, 0)]
        cases += [Case(r["id"], r["question"], r["gold_sql"].rstrip(";"), name) for r in picked]
    return cases


def check_result(
    columns: list[str], rows: list[tuple[Any, ...]], reference_answer: float | None
) -> dict[str, Any]:
    """The checks that can run without a plan: execution, emptiness, truncation, flags, answer."""
    flags: dict[str, int] = {}
    if "quality_flag" in columns:
        index = columns.index("quality_flag")
        for row in rows:
            flags[str(row[index])] = flags.get(str(row[index]), 0) + 1
    matches: bool | None = None
    if reference_answer is not None and rows:
        first = rows[0][0]
        matches = isinstance(first, int | float) and abs(first - reference_answer) < 0.01
    return {
        "non_empty": bool(rows),
        "truncated": len(rows) >= MAX_ROWS,
        "quality_flags": flags or "quality_flag not selected by the query",
        "matches_stored_answer": matches,
    }


def answer_text(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """A template over the result: no figure appears that is not a cell of the result."""
    if not rows:
        return "The query returned no rows."
    shown = "; ".join(
        ", ".join(f"{c} = {v}" for c, v in zip(columns, row, strict=True)) for row in rows[:2]
    )
    return f"{len(rows)} row(s). First: {shown}."


def run_case(
    case: Case,
    tables: list[dict[str, Any]],
    database: ReadOnlyDatabase,
    client: SystemOneClient,
    checkpoint: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    state = {
        "catalogue": catalogue_text(tables),
        "context": render_context(False),
        "user_message": case.question,
    }
    rendered = sum(len(f"{k}: {v}\n") for k, v in state.items())
    routing = client.ask_choice(state, {"domain": ChoiceQuestion.model_validate(domain_question())})
    domain = routing.answers["domain"]
    ranked = rank_tables(tables, domain.choice)
    ids = [t["dataset_id"] for t in ranked]
    entry = next(t for t in tables if t["dataset_id"] == case.dataset)
    record: dict[str, Any] = {
        "case_id": case.case_id,
        "question": case.question,
        "routing": {
            "backend": f"Kev-0.8B ({checkpoint})",
            "domain": domain.choice,
            "probability": round(domain.probabilities[domain.choice], 4),
            "latency_s": round(routing.latency_s, 3),
            "state_chars": rendered,
            "state_within_limit": rendered <= STATE_CHAR_LIMIT,
        },
        "ranking": {
            "tables": ids,
            "expected_table": case.dataset,
            "expected_rank": ids.index(case.dataset) + 1,
            "domain_matches_table": domain.choice == entry["domain"],
        },
        "sql_source": SQL_SOURCE,
        "sql": case.sql,
    }
    try:
        sql_started = time.perf_counter()
        columns, rows = database.run(case.sql)
        record["execution"] = {
            "seconds": round(time.perf_counter() - sql_started, 4),
            "row_count": len(rows),
            "columns": columns,
        }
    except (SqlRejectedError, SqlTimeoutError) as error:
        record |= {"outcome": "failed", "cause": type(error).__name__, "detail": str(error)}
        return record
    record["checks"] = check_result(columns, rows, case.reference_answer)
    record["evidence"] = {
        "dataset_id": entry["dataset_id"],
        "title": entry["title"],
        "publisher": entry["publisher"],
        "licence": entry["licence"],
        "retrieved": entry["retrieved"],
        "dataset_version": entry["dataset_version"],
        "raw_sha256": entry["raw_sha256"],
        "caveats": entry["caveats"],
        "rows_shown": [list(map(str, r)) for r in rows[:3]],
    }
    record["answer"] = answer_text(columns, rows)
    record["outcome"] = "answered" if record["checks"]["non_empty"] else "abstained"
    record["total_seconds"] = round(time.perf_counter() - started, 3)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--base-url", default=os.environ.get("KEV_BASE_URL", "http://localhost:8009")
    )
    parser.add_argument("--checkpoint", default="domain_train250")
    args = parser.parse_args()
    tables = load_catalogue()
    database = ReadOnlyDatabase(
        {t["dataset_id"]: PROCESSED / f"{t['agent_table']}.parquet" for t in tables}
    )
    cases = load_cases({"IMD": 4, "PLFS": 3, "NFHS-5": 3, "Mandi": 2, "NCRB": 2})
    client = SystemOneClient(args.base_url, "kev-latest", os.environ.get("KEV_API_KEY"))
    try:
        records = [run_case(c, tables, database, client, args.checkpoint) for c in cases]
    finally:
        client.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} records to {args.out}")


if __name__ == "__main__":
    main()
