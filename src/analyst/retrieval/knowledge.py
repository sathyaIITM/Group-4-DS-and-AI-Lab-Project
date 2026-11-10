"""Knowledge entries for retrieval: tables, indicators, guidance cards and verified examples.

Every entry is a short structured record built from released artefacts (the catalogue, the
observation tables, the reviewed guidance cards and the approved examples), so no document
chunking is needed. The facts a user receives never come from these entries: they come from
the executed query. The entries tell the hosted LLM where to look and how to query.
"""

import json
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = ROOT / "data" / "processed"
CARDS_PATH = ROOT / "configs" / "rag" / "guidance_cards.v0.json"
EXAMPLES_PATH = ROOT / "data" / "sample" / "rag_verified_examples.v0.jsonl"

EntryKind = Literal["table", "indicator", "card", "example"]


class Entry(BaseModel):
    """One retrievable record. `text` is what is indexed; `payload` is what prompts receive."""

    id: str
    kind: EntryKind
    dataset_id: str | None
    text: str
    payload: dict[str, Any]


def obs_path(dataset_id: str) -> Path:
    return PROCESSED / f"obs_{dataset_id}.parquet"


def _periods(con: duckdb.DuckDBPyConnection, dataset_id: str) -> dict[str, Any]:
    rows = con.execute(
        "SELECT period_type, count(DISTINCT period_label), min(period_label), max(period_label) "
        "FROM read_parquet(?) GROUP BY ALL ORDER BY 1",
        [str(obs_path(dataset_id))],
    ).fetchall()
    return {r[0]: {"labels": r[1], "first": r[2], "last": r[3]} for r in rows}


def table_entries(catalogue: dict[str, Any], con: duckdb.DuckDBPyConnection) -> list[Entry]:
    entries = []
    for t in catalogue["tables"]:
        periods = _periods(con, t["dataset_id"])
        indicators = con.execute(
            "SELECT DISTINCT indicator_label_source FROM read_parquet(?) ORDER BY 1 LIMIT 12",
            [str(obs_path(t["dataset_id"]))],
        ).fetchall()
        labels = "; ".join(r[0] for r in indicators)
        text = (
            f"{t['title']}. Domain {t['domain']}. Publisher {t['publisher']}. "
            f"Geography: {', '.join(t['geo_levels'])}. Coverage {t['coverage_start'][:4]} to "
            f"{t['coverage_end'][:4]}. Indicators: {labels}. Caveats: {' '.join(t['caveats'])}"
        )
        payload = {
            "dataset_id": t["dataset_id"],
            "obs_table": t["obs_table"],
            "title": t["title"],
            "domain": t["domain"],
            "publisher": t["publisher"],
            "licence": t["licence"],
            "dataset_version": t["dataset_version"],
            "retrieved": t["retrieved"],
            "source_table": t["source_table"],
            "geo_levels": t["geo_levels"],
            "periods": periods,
            "indicator_count": t["indicators"],
            "caveats": t["caveats"],
        }
        entries.append(
            Entry(
                id=f"table:{t['dataset_id']}",
                kind="table",
                dataset_id=t["dataset_id"],
                text=text,
                payload=payload,
            )
        )
    return entries


def indicator_entries(catalogue: dict[str, Any], con: duckdb.DuckDBPyConnection) -> list[Entry]:
    entries = []
    for t in catalogue["tables"]:
        rows = con.execute(
            "SELECT indicator_id, any_value(indicator_label_source), any_value(unit) "
            "FROM read_parquet(?) GROUP BY 1 ORDER BY 1",
            [str(obs_path(t["dataset_id"]))],
        ).fetchall()
        for indicator_id, label, unit in rows:
            entries.append(
                Entry(
                    id=f"indicator:{t['dataset_id']}:{indicator_id}",
                    kind="indicator",
                    dataset_id=t["dataset_id"],
                    text=f"{label} ({unit}). {t['title']}",
                    payload={
                        "dataset_id": t["dataset_id"],
                        "indicator_id": indicator_id,
                        "label": label,
                        "unit": unit,
                    },
                )
            )
    return entries


def card_entries(path: Path = CARDS_PATH) -> list[Entry]:
    cards = json.loads(path.read_text(encoding="utf-8"))["cards"]
    return [
        Entry(
            id=f"card:{c['id']}",
            kind="card",
            dataset_id=c["dataset_id"],
            text=f"{c['title']}. {c['body']}",
            payload=c,
        )
        for c in cards
    ]


def example_entries(path: Path = EXAMPLES_PATH) -> list[Entry]:
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            entries.append(
                Entry(
                    id=f"example:{e['id']}",
                    kind="example",
                    dataset_id=e["dataset_id"],
                    text=e["question"],
                    payload=e,
                )
            )
    return entries


def build_entries() -> list[Entry]:
    """All entries of the current release, in a stable order."""
    catalogue = json.loads((PROCESSED / "catalogue.json").read_text(encoding="utf-8"))
    con = duckdb.connect(":memory:")
    try:
        return (
            table_entries(catalogue, con)
            + indicator_entries(catalogue, con)
            + card_entries()
            + example_entries()
        )
    finally:
        con.close()
