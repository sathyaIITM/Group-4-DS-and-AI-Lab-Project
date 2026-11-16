"""Smoke test of intent extraction on the Milestone 3 question set, with the live hosted LLM.

    python scripts/smoke_intent.py                   # plan only: nothing is sent
    python scripts/smoke_intent.py --yes --out outputs/reports/smoke_intent_<date>.json

For each question: the Milestone 3 hybrid retriever returns the top-4 tables, their indicators
and two guidance cards; `extract_intent` (prompt `intent.v1`, model and thinking level from
configs/model.yaml) reads the question into a `QueryIntent`. The output reports whether the
chosen table is the expected one (`data/sample/rag_poc_retrieval_gold.v0.jsonl`), the action,
indicators and operation, the attempts, tokens and estimated cost.

This checks the prompt and the client against the real model; it is not an evaluation result.
Coverage (for example a period outside the table) is decided later by code, so `action` is
reported, not scored.

Safety: nothing is sent without `--yes`; at most MAX_CALLS calls in total (each question may use
one retry); account, project, model and the worst-case cost are printed first.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "sample" / "rag_poc_retrieval_gold.v0.jsonl"
CATALOGUE = ROOT / "data" / "processed" / "catalogue.json"
MAX_CALLS = 30
INDICATORS_PER_TABLE = 6
CATEGORY_VALUES_SHOWN = 30
INPUT_TOKENS_GUESS = 2500  # per call, for the worst-case estimate


def gcloud_value(key: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["gcloud", "config", "get-value", key],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.stdout.strip()


def retrieved_for(index: Any, question: str, tables: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The retrieval output in the shape `extract_intent` expects."""
    table_hits = index.search(question, "table", 4)
    ids = [h.entry.dataset_id for h in table_hits if h.entry.dataset_id]
    entries = []
    for dataset_id in ids:
        entry = dict(next(h.entry.payload for h in table_hits if h.entry.dataset_id == dataset_id))
        entry["coverage_start"] = tables[dataset_id].get("coverage_start")
        entry["coverage_end"] = tables[dataset_id].get("coverage_end")
        entry["period_types"] = tables[dataset_id].get("period_types")
        entries.append(entry)
    indicators = []
    for dataset_id in ids:  # per table, so a table with many indicators cannot crowd out others
        hits = index.search(question, "indicator", INDICATORS_PER_TABLE, dataset_ids={dataset_id})
        indicators += [h.entry.payload for h in hits if h.entry.dataset_id == dataset_id]
    cards = [h.entry.payload.get("body", "") for h in index.search(question, "card", 2)]
    categories = {d: codelists(d, list(tables[d].get("categories") or {}), question) for d in ids}
    return {"tables": entries, "indicators": indicators, "categories": categories, "cards": cards}


def codelists(dataset_id: str, columns: list[str], question: str) -> dict[str, list[str]]:
    """Category values to show: those whose words occur in the question, else the most frequent
    ones (the full codelists are too long for a prompt: Mandi has 548 varieties)."""
    import duckdb

    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) >= 4}
    path = ROOT / "data" / "processed" / f"obs_{dataset_id}.parquet"
    out: dict[str, list[str]] = {}
    with duckdb.connect() as con:
        for column in columns:
            rows = con.execute(
                f"SELECT {column}, count(*) n FROM read_parquet(?) "  # noqa: S608
                f"WHERE {column} IS NOT NULL GROUP BY 1 ORDER BY n DESC",
                [str(path)],
            ).fetchall()
            values = [str(r[0]) for r in rows]
            matched = [v for v in values if words & set(re.findall(r"[a-z0-9]+", v.lower()))]
            out[column] = (matched or values)[:CATEGORY_VALUES_SHOWN]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="send the calls (spends credit)")
    parser.add_argument("--limit", type=int, help="first N questions only")
    parser.add_argument("--only", nargs="+", help="question ids to run, e.g. rp-01 rp-05")
    parser.add_argument(
        "--schema", action="store_true", help="send the JSON Schema (response_format json_schema)"
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    from analyst.inference.intent import extract_intent
    from analyst.inference.llm import LlmClient, LlmError

    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", gcloud_value("project"))
    client = LlmClient.from_config(max_llm_calls=2)
    client.schema_output = client.schema_output or args.schema
    cases = [json.loads(x) for x in GOLD.read_text(encoding="utf-8").splitlines() if x.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    cases = cases[: args.limit]
    effort = client.thinking_level("intent")
    cap = client.output_cap("intent", effort) or 0
    price_in = client.price_per_mtok.get("input") or 0.0
    price_out = client.price_per_mtok.get("output") or 0.0
    worst_calls = 2 * len(cases)
    worst = worst_calls * (INPUT_TOKENS_GUESS * price_in + cap * price_out) / 1e6
    print(f"account  {gcloud_value('account')}\nproject  {os.environ['GOOGLE_CLOUD_PROJECT']}")
    print(f"model    {client.model}  thinking {effort}  output cap {cap}")
    print(f"format   {'json_schema' if client.schema_output else 'json_object'}")
    print(f"questions {len(cases)}; at most {worst_calls} calls; worst-case cost ${worst:.4f}")
    if worst_calls > MAX_CALLS:
        print(f"refused: more than {MAX_CALLS} calls")
        return 2
    if not args.yes:
        print("plan only: nothing sent (add --yes to send)")
        return 0

    from analyst.retrieval.hybrid import HybridIndex, database_url_from_env
    from analyst.retrieval.knowledge import build_entries

    tables = {t["dataset_id"]: t for t in json.loads(CATALOGUE.read_text())["tables"]}
    index = HybridIndex(build_entries(), database_url_from_env())
    index.build()
    rows, total = [], 0.0
    for case in cases:

        class Counter:
            llm_calls = 0

        row: dict[str, Any] = {"id": case["id"], "expected": case["expected_dataset_ids"]}
        attempts: list[Any] = []
        try:
            retrieved = retrieved_for(index, case["question"], tables)
            row["retrieved"] = [t["dataset_id"] for t in retrieved["tables"]]
            row["indicators_shown"] = len(retrieved["indicators"])
            intent, record = extract_intent(case["question"], retrieved, None, client, Counter())
            attempts = [*record.earlier_attempts, record]
            row |= {
                "dataset_id": intent.dataset_id,
                "table_ok": intent.dataset_id in case["expected_dataset_ids"]
                or (not case["expected_dataset_ids"] and intent.dataset_id == "none_fit"),
                "action": intent.action,
                "indicator_ids": intent.indicator_ids,
                "operation": intent.operation,
                "reason": intent.reason,
            }
        except LlmError as error:
            attempts = error.records
            row |= {"error": str(error)[:200], "table_ok": False}
        except Exception as error:  # record and continue with the next question
            row |= {"error": f"{type(error).__name__}: {str(error)[:200]}", "table_ok": False}
        cost = sum(a.cost_usd_est or 0.0 for a in attempts)
        total += cost
        row |= {
            "calls": len(attempts),
            "parse_errors": [a.parse_error for a in attempts if a.parse_error],
            "tokens_in": sum(a.tokens_in for a in attempts),
            "tokens_out": sum(a.tokens_out for a in attempts),
            "thinking_tokens": sum(a.reasoning_tokens or 0 for a in attempts),
            "latency_ms": sum(a.latency_ms for a in attempts),
            "cost_usd_est": round(cost, 6),
        }
        rows.append(row)
        print(json.dumps(row))
    ok = sum(1 for r in rows if r.get("table_ok"))
    print(f"table chosen correctly: {ok} of {len(rows)}; total estimated cost ${total:.5f}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "model": client.model,
                    "response_format": "json_schema" if client.schema_output else "json_object",
                    "thinking": effort,
                    "output_cap": cap,
                    "table_ok": ok,
                    "questions": len(rows),
                    "total_cost_usd_est": total,
                    "rows": rows,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
