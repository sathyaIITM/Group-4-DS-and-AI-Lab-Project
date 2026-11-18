"""Deterministic place resolution against catalogue table values and reference aliases."""

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Mapping
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
        pairs: Iterable[tuple[Any, Any]]
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
    key = (dataset_id, level, version)
    if key not in _PLACE_CACHE:
        rows = db.execute(
            f"SELECT DISTINCT geo_name FROM {table} WHERE geo_level = ? "  # noqa: S608 - validated table identifier
            "AND geo_name IS NOT NULL ORDER BY geo_name",
            [level],
        ).fetchall()
        _PLACE_CACHE[key] = tuple(str(row[0]) for row in rows)
    return list(_PLACE_CACHE[key])


# Keyed by dataset version, not by connection: a new read-only database is opened per node call.
_PLACE_CACHE: dict[tuple[str, str, str], tuple[str, ...]] = {}


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
    same = [row for row in candidates if row[1] == target] or [
        row for row in candidates if normalise(row[1]) == normalise(target)
    ]
    if len(same) > 1:  # one name, several places (Aurangabad, Bihar and Maharashtra)
        return PlaceResolution(
            status="unresolved", options=[f"{name} ({code})" for code, name, _ in same][:6]
        )
    if not same:
        # A table name that extends the asked name ("Jammu and Kashmir" in the SRS table is
        # "Jammu and Kashmir Including Ladakh" before 2019): accepted only when it is unique.
        longer = [
            r for r in candidates if normalise(r[1]).startswith(normalise(target) + " including ")
        ]
        same = longer if len(longer) == 1 else []
    exact = same[0] if same else None
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


# Rows of finer tables carry their State (and district), so these levels act as filters.
FILTER_LEVELS = {"district": ("state",), "market": ("state", "district")}


def resolve_filter_place(
    mention: str, dataset_id: str, level: str, refs: Mapping[str, Any], db: Any
) -> PlaceResolution:
    """Resolve a State or district named on a finer table through its ``geo_<level>`` column."""
    if level not in {"state", "district"}:
        raise ValueError("filter level must be state or district")
    table = _table(dataset_id)
    rows = db.execute(
        f"SELECT DISTINCT geo_{level} FROM {table} "  # noqa: S608 - validated identifiers
        f"WHERE geo_{level} IS NOT NULL ORDER BY 1"
    ).fetchall()
    names = [str(row[0]) for row in rows]
    alias = alias_lookup(mention, refs)
    target = alias if alias in names else mention
    found = [name for name in names if normalise(name) == normalise(target)]
    if len(found) != 1:
        return PlaceResolution(status="unresolved")
    name = found[0]
    matched: Literal["exact", "alias"] = "exact" if name == mention else "alias"
    return PlaceResolution(
        status=matched,
        place=Place(
            requested=mention,
            level=level,
            code=f"{level}:{normalise(name).replace(' ', '_')}",
            name=name,
            match=matched,
        ),
    )


# What users write for the national row ("All India", "rural India"); the sector or area word is
# a category, which intent extraction records separately.
NATIONAL_MENTIONS = {
    "india",
    "all india",
    "all of india",
    "national",
    "nationwide",
    "the country",
    "country",
    "bharat",
    "rural india",
    "urban india",
    "all india level",
}


def is_national(mention: str) -> bool:
    return normalise(mention) in NATIONAL_MENTIONS


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
