"""Retrieval context in the shape the T3 prompts expect (`inference.intent.context_payload`).

Built from the published catalogue (`data/processed/catalogue.json`). Indicator labels and
category codelists come from the observation table when it is present; otherwise an indicator is
shown by its id and a category column has no codelist (the intent validator then rejects category
values, which is the safe direction).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from analyst.decisions.coverage import load_published

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
        rows = duckdb.execute(
            "SELECT DISTINCT indicator_id, indicator_label_source "  # noqa: S608
            f"FROM read_parquet('{_obs(dataset_id)}')"
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


def codelists_of(table: dict[str, Any]) -> dict[str, list[str]]:
    dataset_id = table["dataset_id"]
    out: dict[str, list[str]] = {}
    if not _obs(dataset_id).exists():
        return out
    for column, count in (table.get("categories") or {}).items():
        if isinstance(count, int) and count <= MAX_CODELIST:
            rows = duckdb.execute(
                f"SELECT DISTINCT \"{column}\" FROM read_parquet('{_obs(dataset_id)}') "  # noqa: S608
                f'WHERE "{column}" IS NOT NULL ORDER BY 1'
            ).fetchall()
            out[column] = [str(r[0]) for r in rows]
    return out


def table_context(published: dict[str, dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    """`tables`, `indicators` and `categories` for the candidate tables, in candidate order."""
    tables = [published[i] for i in ids if i in published]
    return {
        "tables": [{k: t[k] for k in TABLE_FIELDS if k in t} for t in tables],
        "indicators": [ind for t in tables for ind in indicators_of(t)],
        "categories": {t["dataset_id"]: codelists_of(t) for t in tables},
    }
