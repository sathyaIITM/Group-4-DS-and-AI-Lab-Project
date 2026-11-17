"""Deterministic place resolution against catalogue table values and reference aliases."""

from __future__ import annotations

import re
import string
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import Field

from analyst.contracts import Contract, Place


class PlaceResolution(Contract):
    """Result of resolving a place mention; unresolved mentions never use fuzzy matches."""

    status: Literal["exact", "alias", "unresolved"]
    place: Place | None = None
    options: list[str] = Field(default_factory=list)


def normalise(name: str) -> str:
    """Return a case-folded place key with punctuation and repeated whitespace normalised."""
    expanded = name.replace("&", " and ").replace("\xa0", " ").casefold()
    normalised = "".join(" " if c in string.punctuation else c for c in expanded)
    return re.sub(r"\s+", " ", normalised).strip()


def alias_lookup(name: str, refs: Mapping[str, Any]) -> str | None:
    """Look up an alias in mappings or tabular reference data, returning its canonical name."""
    key = normalise(name)
    for ref_name in ("place_aliases", "subdivision_aliases"):
        ref = refs.get(ref_name)
        if ref is None:
            continue
        if isinstance(ref, Mapping):
            pairs = ref.items()
        elif isinstance(ref, pd.DataFrame):
            pairs = zip(ref["alias"], ref["canonical"], strict=True)
        else:
            frame = pd.read_csv(Path(ref), dtype=str)
            pairs = zip(frame["alias"], frame["canonical"], strict=True)
        for alias, canonical in pairs:
            if normalise(str(alias)) == key:
                return str(canonical)
    return None


def _table(dataset_id: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", dataset_id):
        raise ValueError("dataset_id must be a lowercase identifier")
    return f"obs_{dataset_id}"


def places_in_table(dataset_id: str, level: str, db: Any) -> list[str]:
    """Return sorted distinct names for a geographic level from an observation table."""
    table = _table(dataset_id)
    version_row = db.execute(
        f"SELECT DISTINCT dataset_version FROM {table} ORDER BY dataset_version DESC LIMIT 1"  # noqa: S608 - validated table identifier
    ).fetchone()
    version = str(version_row[0]) if version_row and version_row[0] is not None else "unknown"
    return list(_cached_places(dataset_id, level, version, db))


@lru_cache(maxsize=512)
def _cached_places(dataset_id: str, level: str, version: str, db: Any) -> tuple[str, ...]:
    """Cache names for one live database connection, dataset version, and geography level."""
    table = _table(dataset_id)
    rows = db.execute(
        f"SELECT DISTINCT geo_name FROM {table} WHERE geo_level = ? "  # noqa: S608 - validated table identifier
        "AND geo_name IS NOT NULL ORDER BY geo_name",
        [level],
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def resolve_place(
    mention: str,
    dataset_id: str,
    level: str,
    refs: Mapping[str, Any],
    db: Any,
) -> PlaceResolution:
    """Resolve exact, alias, or case/spacing matches; return prefix options without guessing."""
    table = _table(dataset_id)
    rows = db.execute(
        f"SELECT DISTINCT geo_code, geo_name, geo_vintage FROM {table} "  # noqa: S608 - validated table identifier
        "WHERE geo_level = ? AND geo_name IS NOT NULL ORDER BY geo_name",
        [level],
    ).fetchall()
    candidates = [(str(code), str(name), vintage) for code, name, vintage in rows]
    names = {name for _, name, _ in candidates}
    alias = alias_lookup(mention, refs)
    target = alias if alias in names else mention
    exact = next((row for row in candidates if row[1] == target), None)
    if exact is None:
        key = normalise(target)
        exact = next((row for row in candidates if normalise(row[1]) == key), None)
    if exact is not None:
        code, name, vintage = exact
        matched = "exact" if name == mention and alias is None else "alias"
        return PlaceResolution(
            status=matched,
            place=Place(
                requested=mention,
                level=level,
                code=code,
                name=name,
                match=matched,
                vintage=str(vintage) if vintage is not None else None,
            ),
        )
    key = normalise(mention)
    options = [name for _, name, _ in candidates if normalise(name).startswith(key)][:6]
    return PlaceResolution(status="unresolved", options=options)


def map_state_to_subdivisions(state: str, refs: Mapping[str, Any]) -> list[str]:
    """Return explicitly mapped IMD subdivisions; fail if the reference lacks state mappings."""
    ref = refs.get("imd_subdivisions")
    if ref is None:
        raise ValueError("imd_subdivisions reference is required")
    frame = ref.copy() if isinstance(ref, pd.DataFrame) else pd.read_csv(Path(ref), dtype=str)
    state_key = normalise(state)
    column = next((c for c in ("state", "state_name", "states") if c in frame.columns), None)
    if column is None:
        raise ValueError("imd_subdivisions reference does not contain state mappings")
    return sorted(
        str(row["subdivision"])
        for _, row in frame.iterrows()
        if state_key in {normalise(part) for part in re.split(r"[;,|]", str(row[column]))}
    )
