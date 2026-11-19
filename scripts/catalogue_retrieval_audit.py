"""Catalogue retrieval audit: can the agent's retriever find the table for every indicator and
every crop and commodity value of the release? Questions are generated from the catalogue
itself (no LLM, no evaluation set), so the check is exhaustive for the published tables and is
rerun whenever a table is added.

    python scripts/catalogue_retrieval_audit.py
        [--out outputs/reports/catalogue_retrieval_audit.json]
        [--paraphrases data/eval/retrieval_paraphrase_dev.v1.jsonl]

Indicator questions are asked bare and with a place at each geography level of the table; a
question counts as found when any table carrying that indicator (at that level) is in the top 4.
The paraphrase set (hand-written, development only) is scored as any expected table in the top 4.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

from analyst.agents.control_nodes import rank_catalogue

TOP_K = 4
parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
parser.add_argument(
    "--out", type=Path, default=Path("outputs/reports/catalogue_retrieval_audit.json")
)
parser.add_argument(
    "--paraphrases", type=Path, default=Path("data/eval/retrieval_paraphrase_dev.v1.jsonl")
)
args = parser.parse_args()
OUT = args.out
cat = json.loads(Path("data/processed/catalogue.json").read_text())
tables = {t["dataset_id"]: t for t in cat["tables"]}
PLACE = {
    "district": "Kozhikode",
    "state": "Bihar",
    "national": "India",
    "market": "Azadpur",
    "subdivision": "Coastal Karnataka",
}


def clean(label: str) -> str:
    """Strip footnote markers and percent suffixes from an indicator label."""
    label = re.sub(r"(?<=[A-Za-z)%])\d+\b", "", label)  # footnote markers: "cooking3"
    label = re.sub(r"\s*\((?:%|per cent|percent)\)\s*$", "", label)
    return re.sub(r"\s+", " ", label).strip(" .")


def obs(dataset_id: str) -> str:
    """Return the path of a dataset's observation table."""
    return f"data/processed/obs_{dataset_id}.parquet"


# indicator label -> tables that carry it (the NFHS State and district factsheets share many)
carriers: dict[str, set[str]] = defaultdict(set)
rows = []
for table_id in tables:
    for indicator_id, label in duckdb.execute(
        "SELECT indicator_id, any_value(indicator_label_source) FROM read_parquet(?) "
        "GROUP BY 1 ORDER BY 1",
        [obs(table_id)],
    ).fetchall():
        rows.append((table_id, indicator_id, clean(str(label))))
        carriers[clean(str(label)).casefold()].add(table_id)


COLUMNS = {"crop", "commodity_name"}


def values(dataset_id: str, column: str) -> list[str]:
    """Return the distinct values of an allowed column of a table."""
    if column not in COLUMNS:
        raise ValueError(f"unexpected column {column!r}")
    sql = f"SELECT DISTINCT {column} FROM read_parquet(?) WHERE {column} IS NOT NULL ORDER BY 1"  # noqa: S608 - column from COLUMNS
    return [str(r[0]) for r in duckdb.execute(sql, [obs(dataset_id)]).fetchall()]


cases = []
for table_id, indicator_id, label in rows:
    cases.append(
        {
            "kind": "indicator",
            "dataset": table_id,
            "item": indicator_id,
            "q": f"What is the {label}?",
            "ok": sorted(carriers[label.casefold()]),
        }
    )
    for level in tables[table_id]["geo_levels"]:
        ok = sorted(t for t in carriers[label.casefold()] if level in tables[t]["geo_levels"])
        cases.append(
            {
                "kind": f"indicator+{level}",
                "dataset": table_id,
                "item": indicator_id,
                "q": f"What is the {label} in {PLACE[level]}?",
                "ok": ok,
            }
        )
for crop in values("crop_production_district", "crop"):
    cases.append(
        {
            "kind": "crop",
            "dataset": "crop_production_district",
            "item": crop,
            "q": f"How much {crop} was produced in 2015-16?",
            "ok": ["crop_production_district"],
        }
    )
for comm in values("mandi_daily_prices", "commodity_name"):
    cases.append(
        {
            "kind": "commodity",
            "dataset": "mandi_daily_prices",
            "item": comm,
            "q": f"What is the market price of {comm}?",
            "ok": ["mandi_daily_prices"],
        }
    )
for comm in values("msp_crops", "commodity_name"):
    cases.append(
        {
            "kind": "msp",
            "dataset": "msp_crops",
            "item": comm,
            "q": f"What is the minimum support price of {comm}?",
            "ok": ["msp_crops"],
        }
    )

by_kind: dict[str, Counter] = defaultdict(Counter)
misses = []
for case in cases:
    ranking, method = rank_catalogue(case["q"], TOP_K)
    top = [name for name, _ in ranking][:TOP_K]
    hit = bool(set(case["ok"]) & set(top))
    rank = next((i + 1 for i, n in enumerate(n for n, _ in ranking) if n in case["ok"]), None)
    by_kind[case["kind"]]["hit" if hit else "miss"] += 1
    if not hit:
        misses.append({**case, "top": top, "rank": rank, "method": method})

summary = {
    k: {"n": v["hit"] + v["miss"], "recall_at_4": round(v["hit"] / (v["hit"] + v["miss"]), 3)}
    for k, v in sorted(by_kind.items())
}
per_table = Counter(miss["dataset"] for miss in misses)
if args.paraphrases.exists():
    found = 0
    for line in args.paraphrases.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        ranking, method = rank_catalogue(item["question"], TOP_K)
        top = [name for name, _ in ranking][:TOP_K]
        if set(item["expected_dataset_ids"]) & set(top):
            found += 1
        else:
            misses.append(
                {
                    "kind": "paraphrase",
                    "dataset": item["expected_dataset_ids"][0],
                    "item": item["id"],
                    "q": item["question"],
                    "top": top,
                    "method": method,
                }
            )
        by_kind["paraphrase"][
            "hit" if set(item["expected_dataset_ids"]) & set(top) else "miss"
        ] += 1
    summary["paraphrase"] = {
        "n": sum(by_kind["paraphrase"].values()),
        "recall_at_4": round(found / sum(by_kind["paraphrase"].values()), 3),
    }
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps({"summary": summary, "misses_by_table": per_table, "misses": misses}, indent=2)
    + "\n",
    encoding="utf-8",
)
print(json.dumps(summary, indent=1))
print("misses by table:", dict(per_table))
for miss in misses[:25]:
    print(
        f"  {miss['kind']:20s} {miss['dataset'][:22]:22s} rank={miss['rank']} "
        f"{miss['q'][:70]!r} -> {miss['top']}"
    )
