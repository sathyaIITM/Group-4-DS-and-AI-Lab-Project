"""Catalogue retrieval for routing and intent extraction (design Section 5, Phase B).

Tables are ranked by the hybrid index of Milestone 3 (BM25 fused with `bge-small-en-v1.5`
similarity, in memory) over one entry per table. Two additions close the gaps found on
`e2e_dev`:

1. Indicator slots: every table carrying the best-matching indicator joins the top k, taking
   the last places (a factsheet whose table entry lists only a few of its 131 indicators; the
   NFHS State and district factsheets carry the same indicators).
2. Glossary: Hindi and Hinglish data words in the question ("berozgari", "mehngai") add their
   English terms to the retrieval query only (`configs/reference/query_glossary.csv`); the
   question passed to the LLM is unchanged.

3. Place slot: sub-division, district and market names read from the tables themselves
   (State names excluded, since every State-level table has them): when no top-k table holds
   a named place, the best-ranked table that does takes a place ("Vidarbha" -> IMD
   sub-divisions, "Lasalgaon" -> mandi prices).

The domain label never filters candidates. If the embedding model cannot be loaded, the caller
falls back to lexical ranking and records that in the run log.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path

import duckdb

from analyst.retrieval.hybrid import HybridIndex
from analyst.retrieval.knowledge import PROCESSED, indicator_entries, table_entries

ROOT = Path(__file__).resolve().parents[3]
GLOSSARY = ROOT / "configs" / "reference" / "query_glossary.csv"
STATES = ROOT / "configs" / "reference" / "states.csv"
PLACE_LEVELS = ("district", "subdivision", "market")
# Market-name suffixes, and words that are place names but also ordinary question words.
_SUFFIX = re.compile(r"\s*\(.*?\)\s*|\b(?:apmc|market|mandi|grain market|f&v|veg market)\b")
_COMPASS = ("north", "south", "east", "west")
_NOT_PLACES = {"mandi", "market", "central", "city", *_COMPASS} | {
    f"{a} {b}" for a in _COMPASS for b in _COMPASS if a != b
}  # "north east" and "south west" are monsoon names as well as IMD sub-divisions
DEPTH = 20
_BUILD = threading.Lock()  # one index build, even when questions run in parallel threads


def load_glossary(path: Path = GLOSSARY) -> list[tuple[str, str]]:
    """(term, expansion) pairs; terms are matched as whole words, case-insensitively."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [(row["term"].casefold(), row["expansion"]) for row in csv.DictReader(handle)]


def expand_query(question: str, glossary: list[tuple[str, str]]) -> str:
    """Append the English terms of glossary words found in the question."""
    text = question.casefold()
    extra = [
        expansion
        for term, expansion in glossary
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text)
    ]
    return " ".join([question, *dict.fromkeys(extra)])


def _label_key(label: object) -> str:
    """Indicator label without footnote markers or case ("cooking3" -> "cooking")."""
    text = re.sub(r"(?<=[A-Za-z)%])\d+\b", "", str(label))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _norm(text: str) -> str:
    """Return lower-case text with punctuation replaced by spaces."""
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


@lru_cache(maxsize=2)
def _gazetteer(release: str, processed: str) -> tuple[dict[str, frozenset[str]], tuple[str, ...]]:
    """Normalised sub-State place name -> tables whose rows carry it; and the State names."""
    states: set[str] = set()
    if STATES.exists():
        with STATES.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                states |= {_norm(str(v)) for v in row.values() if v}
    catalogue = json.loads((Path(processed) / "catalogue.json").read_text(encoding="utf-8"))
    places: dict[str, set[str]] = {}
    con = duckdb.connect(":memory:")
    try:
        for table in catalogue["tables"]:
            path = Path(processed) / f"obs_{table['dataset_id']}.parquet"
            levels = [lvl for lvl in table.get("geo_levels", []) if lvl in PLACE_LEVELS]
            if not levels or not path.exists():
                continue
            rows = con.execute(
                "SELECT DISTINCT geo_name FROM read_parquet(?) WHERE geo_level IN "  # noqa: S608 - only ? placeholders
                f"({', '.join('?' for _ in levels)}) AND geo_name IS NOT NULL",
                [str(path), *levels],
            ).fetchall()
            for (name,) in rows:
                key = _norm(_SUFFIX.sub(" ", str(name)))
                if len(key) >= 4 and key not in states and key not in _NOT_PLACES:
                    places.setdefault(key, set()).add(str(table["dataset_id"]))
    finally:
        con.close()
    long_first = tuple(sorted((s for s in states if s), key=len, reverse=True))
    return {name: frozenset(tables) for name, tables in places.items()}, long_first


def place_ranking(question: str, processed: Path = PROCESSED) -> list[str]:
    """Tables carrying the sub-State places named in the question, most matches first."""
    gazetteer, states = _gazetteer(_release_key(processed), str(processed))
    text = f" {_norm(question)} "
    named_states = [state for state in states if f" {state} " in text]
    counts: dict[str, int] = {}
    for name, tables in gazetteer.items():
        if f" {name} " not in text:
            continue
        # "Jammu" inside "Jammu and Kashmir" is the State, not the district.
        if any(f" {name} " in f" {state} " for state in named_states):
            continue
        for table in tables:
            counts[table] = counts.get(table, 0) + 1
    return sorted(counts, key=lambda t: -counts[t])


def _release_key(processed: Path) -> str:
    """Return the hash that identifies a catalogue release."""
    return hashlib.sha256((processed / "catalogue.json").read_bytes()).hexdigest()


@lru_cache(maxsize=2)
def _index(release: str, processed: str) -> HybridIndex:
    """One in-memory index per catalogue release (keyed by the catalogue file hash)."""
    catalogue = json.loads((Path(processed) / "catalogue.json").read_text(encoding="utf-8"))
    con = duckdb.connect(":memory:")
    try:
        entries = table_entries(catalogue, con) + indicator_entries(catalogue, con)
    finally:
        con.close()
    index = HybridIndex(entries, None)
    index.build()
    return index


def rank_tables(
    question: str, k: int, processed: Path = PROCESSED, depth: int = DEPTH
) -> list[tuple[str, float]]:
    """Dataset ids with fused scores, best first; the last places may be indicator slots."""
    with _BUILD:
        index = _index(_release_key(processed), str(processed))
        _gazetteer(_release_key(processed), str(processed))
    query = expand_query(question, load_glossary())
    hits = index.search(query, "table", depth)
    ranked = [(str(h.entry.dataset_id), float(h.score)) for h in hits if h.entry.dataset_id]
    order = [d for d, _ in ranked]
    slots: list[str] = []
    # Place slot first: the best-ranked table holding a named sub-State place (a named market
    # or sub-division is the strongest evidence of the table).
    by_place = place_ranking(question, processed)
    if by_place:
        slots.append(min(by_place, key=lambda d: order.index(d) if d in order else len(order)))
    # Indicator slots: every table carrying one of the two best indicators (the NFHS State and
    # district factsheets carry the same indicators).
    for hit in index.search(query, "indicator", 2):
        label = _label_key(hit.entry.payload.get("label", ""))
        slots += [
            str(e.dataset_id)
            for e in index.entries
            if e.kind == "indicator" and _label_key(e.payload.get("label", "")) == label
        ]
    return _with_slots(ranked, list(dict.fromkeys(slots)), k)


def _with_slots(
    ranked: list[tuple[str, float]], slots: list[str], k: int
) -> list[tuple[str, float]]:
    """Keep up to k - 1 slot tables in the top k; fill the other places from the ranking."""
    top = [d for d, _ in ranked[:k]]
    chosen = list(dict.fromkeys(slots))[: max(k - 1, 0)]
    if all(d in top for d in chosen):
        return ranked
    score = dict(ranked)
    floor = ranked[min(k, len(ranked)) - 1][1] if ranked else 0.0
    fill = [d for d, _ in ranked if d not in chosen][: k - len(chosen)]
    order = [d for d, _ in ranked]
    head = sorted([*fill, *chosen], key=lambda d: order.index(d) if d in order else len(order))
    rest = [(d, s) for d, s in ranked if d not in head]
    return [(d, score.get(d, floor)) for d in head] + rest


def warm_up(processed: Path = PROCESSED) -> None:
    """Load the embedding model and build the index before the first question (cold start)."""
    rank_tables("warm up", 4, processed)


__all__ = ["expand_query", "load_glossary", "place_ranking", "rank_tables", "warm_up"]
