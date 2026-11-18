"""Retrieval context in the shape the T3 prompts expect (`inference.intent.context_payload`).

Built from the published catalogue (`data/processed/catalogue.json`). Indicator labels and
category codelists come from the observation table when it is present; otherwise an indicator is
shown by its id and a category column has no codelist (the intent validator then rejects category
values, which is the safe direction).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb

from analyst.decisions.coverage import load_published
from analyst.retrieval.catalogue import expand_query, load_glossary
from analyst.tools.codelists import codelist, named_values

PUBLISHED = Path("data/processed/catalogue.json")
TABLE_FIELDS = (
    "dataset_id",
    "title",
    "geo_levels",
    "coverage_start",
    "coverage_end",
    "period_types",
    "caveats",
    "domain",
)
MAX_CODELIST = 50


def published_catalogue(path: Path = PUBLISHED) -> dict[str, dict[str, Any]]:
    """The published tables by dataset id; empty when no release is present."""
    return load_published(path) if path.exists() else {}


def _obs(dataset_id: str) -> Path:
    return PUBLISHED.parent / f"obs_{dataset_id}.parquet"


def indicators_of(table: dict[str, Any]) -> list[dict[str, str]]:
    dataset_id = table["dataset_id"]
    units: dict[str, str] = table.get("indicator_units", {})
    labels: dict[str, str] = {}
    if _obs(dataset_id).exists():
        with duckdb.connect() as con:  # own connection: questions run in parallel threads
            rows = con.execute(
                "SELECT DISTINCT indicator_id, indicator_label_source FROM read_parquet(?)",
                [str(_obs(dataset_id))],
            ).fetchall()
        labels = {r[0]: r[1] for r in rows}
    return [
        {
            "dataset_id": dataset_id,
            "indicator_id": i,
            "label": labels.get(i) or i,
            "unit": unit,
        }
        for i, unit in units.items()
    ]


def codelists_of(table: dict[str, Any], question: str = "") -> dict[str, list[str]]:
    """Short codelists in full; a long one only through the values the question names."""
    dataset_id = table["dataset_id"]
    out: dict[str, list[str]] = {}
    if not _obs(dataset_id).exists():
        return out
    asked = expand_query(question, load_glossary()) if question else ""
    for column in table.get("categories") or {}:
        values = codelist(dataset_id, column, PUBLISHED.parent)
        if len(values) <= MAX_CODELIST:
            out[column] = values
        else:
            named = named_values(values, asked)
            if named:
                out[column] = named
    return out


def catalogue_block(path: Path = PUBLISHED) -> dict[str, Any]:
    """Every published dataset with its indicators and short codelists, in catalogue order.

    Identical for every question of a release, so it opens the intent prompt (v5) and the
    provider's implicit cache can serve it (a prefix of at least 4,096 tokens is needed).
    """
    if not path.exists():
        return {}
    return _catalogue_block(hashlib.sha256(path.read_bytes()).hexdigest(), str(path))


@lru_cache(maxsize=2)
def _catalogue_block(release: str, path: str) -> dict[str, Any]:
    from analyst.inference.intent import context_payload

    published = published_catalogue(Path(path))
    payload = context_payload(table_context(published, list(published)))
    return {k: payload[k] for k in ("datasets", "indicators", "category_values")}


def table_context(
    published: dict[str, dict[str, Any]], ids: list[str], question: str = ""
) -> dict[str, Any]:
    """`tables`, `indicators` and `categories` for the candidate tables, in candidate order."""
    tables = [published[i] for i in ids if i in published]
    return {
        "tables": [{k: t[k] for k in TABLE_FIELDS if k in t} for t in tables],
        "indicators": [ind for t in tables for ind in indicators_of(t)],
        "categories": {t["dataset_id"]: codelists_of(t, question) for t in tables},
    }
