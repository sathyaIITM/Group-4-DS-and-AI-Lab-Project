"""Category codelists of the published tables.

The catalogue stores a short codelist as a count when it is long (`commodity_name: 261`); the
values are read from the observation table and cached per file version. The intent context
shows a long codelist only through the values the question names, so the prompt stays short and
the model can still filter on them ("potato" -> `Potato`; "gehun" -> `Wheat` via the glossary).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import duckdb

PROCESSED = Path("data/processed")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


@lru_cache(maxsize=64)
def _read(path: str, column: str, mtime: float) -> tuple[str, ...]:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", column):
        raise ValueError(f"invalid column name: {column!r}")
    sql = f'SELECT DISTINCT "{column}" FROM read_parquet(?) WHERE "{column}" IS NOT NULL ORDER BY 1'  # noqa: S608 - validated identifier
    with duckdb.connect() as con:  # not the shared default connection: runs are threaded
        return tuple(str(row[0]) for row in con.execute(sql, [path]).fetchall())


def codelist(dataset_id: str, column: str, processed: Path = PROCESSED) -> list[str]:
    """Every value of a category column; [] when the table is not present."""
    path = processed / f"obs_{dataset_id}.parquet"
    if not path.exists():
        return []
    return list(_read(str(path), column, path.stat().st_mtime))


def named_values(values: list[str], question: str) -> list[str]:
    """Values the question names: the whole value, its part before a bracket, or the bracketed
    part ("Bhindi(Ladies Finger)" matches "ladies finger"), as whole words."""
    text = f" {_norm(question)} "
    found = []
    for value in values:
        forms = {value, re.sub(r"\(.*?\)", " ", value), *re.findall(r"\((.*?)\)", value)}
        if any((key := _norm(form)) and len(key) >= 3 and f" {key} " in text for form in forms):
            found.append(value)
    return found


__all__ = ["codelist", "named_values"]
