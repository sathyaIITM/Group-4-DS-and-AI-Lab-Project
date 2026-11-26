"""Structured gold fields of an end-to-end evaluation item, derived from its gold SQL.

Scorer v3 checks the agent's interpretation (places, periods, indicators), the completeness and
the unit of an answer against fields of the gold item. Five of them follow from the gold query and
are filled here, never typed by hand:

| Field | Value |
| --- | --- |
| `expected_places` | Distinct `{"name", "level"}` of the gold rows (`geo_name`, `geo_level`) |
| `expected_periods` | Distinct `{"start", "end"}` of the gold rows, ISO dates |
| `indicator_ids` | Distinct `indicator_id` of the gold rows |
| `unit` | Distinct `unit` of the gold rows (joined with "; " if several) |
| `n_values` | Non-null cells of the `value` column of the gold result, before any derivation |
| `gold_lineage` | `rows` (fields describe the gold rows) or `inputs` (inputs of an aggregate) |

The rows are traced in one of two ways. A plain query (no aggregate, no DISTINCT, one table) is run
again with the lineage columns appended to its projection, so ORDER BY and LIMIT keep exactly the
gold rows (`mode = "rows"`). An aggregate or DISTINCT query is traced through its input rows: the
same FROM and WHERE without grouping, ordering or limit (`mode = "inputs"`). A UNION traces each
branch. Anything else is reported as unsupported and left for the author.

Fields filled by hand (`domain`, `clarify_slot`, `clarify_options`) are only added as `null`
placeholders when absent. A field that already holds a value is never overwritten unless asked;
a differing computed value is reported instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import sqlglot
from sqlglot import exp

from analyst.tools.sql_runner import ReadOnlyDatabase

SCRIPT_FIELDS = (
    "expected_places",
    "expected_periods",
    "indicator_ids",
    "unit",
    "n_values",
    "gold_lineage",
)
HAND_FIELDS = ("domain", "clarify_slot", "clarify_options")
LINEAGE = {
    "__geo_name": "geo_name",
    "__geo_level": "geo_level",
    "__period_start": "period_start",
    "__period_end": "period_end",
    "__indicator_id": "indicator_id",
    "__unit": "unit",
}


@dataclass
class ItemFields:
    """Computed fields of one item, with how they were traced and any problem found."""

    item_id: str
    fields: dict[str, Any]
    mode: str
    problems: list[str] = field(default_factory=list)


def _lineage_columns() -> list[exp.Expr]:
    """Return the lineage projections, aliased so they cannot clash with gold aliases."""
    return [exp.alias_(exp.column(source), alias) for alias, source in LINEAGE.items()]


def _single_table(select: exp.Select) -> bool:
    """Return True when the outer query reads one table with no join or subquery."""
    tables = {t.name.lower() for t in select.find_all(exp.Table)}
    subqueries = len(list(select.find_all(exp.Select))) > 1
    return not select.args.get("joins") and len(tables) == 1 and not subqueries


def lineage_queries(gold_sql: str) -> tuple[list[str], str]:
    """Return the lineage queries for a gold query and the tracing mode.

    Mode is `rows`, `inputs` or `unsupported` (then the list is empty).
    """
    tree = sqlglot.parse_one(gold_sql, read="duckdb")
    if isinstance(tree, exp.Union):
        branches = [tree.left, tree.right]
        queries: list[str] = []
        modes: set[str] = set()
        for branch in branches:
            sub, mode = lineage_queries(branch.sql(dialect="duckdb"))
            if mode == "unsupported":
                return [], "unsupported"
            queries += sub
            modes.add(mode)
        return queries, "inputs" if "inputs" in modes else "rows"
    if not isinstance(tree, exp.Select) or tree.args.get("with") or tree.args.get("joins"):
        return [], "unsupported"
    has_aggregate = tree.find(exp.AggFunc) is not None or bool(tree.args.get("group"))
    has_distinct = bool(tree.args.get("distinct"))
    if not has_aggregate and not has_distinct and _single_table(tree):
        traced = tree.copy().select(*_lineage_columns(), append=True)
        return [traced.sql(dialect="duckdb")], "rows"
    source = tree.find(exp.From)
    if source is None:
        return [], "unsupported"
    inputs = exp.select(*_lineage_columns()).from_(source.this.copy()).distinct()
    where = tree.args.get("where")
    if where is not None:
        inputs = inputs.where(where.this.copy())
    return [inputs.sql(dialect="duckdb")], "inputs"


def _iso(value: Any) -> str | None:
    """Return an ISO date for a date or timestamp cell."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _distinct(values: list[Any]) -> list[Any]:
    """Return the values without repeats, in first-seen order."""
    seen: list[Any] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def compute_fields(item: dict[str, Any], database: ReadOnlyDatabase) -> ItemFields:
    """Compute the script fields of one item; non-answer items get empty values."""
    item_id = str(item.get("id", "?"))
    sql = item.get("gold_sql")
    if item.get("expected_action") != "answer" or not sql:
        empty: dict[str, Any] = {
            "expected_places": [],
            "expected_periods": [],
            "indicator_ids": [],
            "unit": None,
            "n_values": 0,
            "gold_lineage": None,
        }
        return ItemFields(item_id, empty, "no_sql")
    problems: list[str] = []
    columns, rows = database.run(sql)
    if "value" in columns:
        position = columns.index("value")
        n_values = sum(1 for row in rows if row[position] is not None)
    else:
        n_values = len(rows)
        problems.append("gold result has no value column; n_values counts rows")
    queries, mode = lineage_queries(sql)
    if mode == "unsupported":
        problems.append("query shape not traced (CTE or join); fill places and periods by hand")
        return ItemFields(item_id, {"n_values": n_values}, mode, problems)
    records: list[dict[str, Any]] = []
    for query in queries:
        names, lineage_rows = database.run(query)
        records += [dict(zip(names, row, strict=True)) for row in lineage_rows]
    places = _distinct(
        [
            {"name": r["__geo_name"], "level": r["__geo_level"]}
            for r in records
            if r["__geo_name"] is not None
        ]
    )
    periods = _distinct(
        [
            {"start": _iso(r["__period_start"]), "end": _iso(r["__period_end"])}
            for r in records
            if r["__period_start"] is not None
        ]
    )
    indicators = _distinct([r["__indicator_id"] for r in records if r["__indicator_id"]])
    units = _distinct([r["__unit"] for r in records if r["__unit"]])
    if not records:
        problems.append("lineage query returned no rows")
    computed = {
        "expected_places": places,
        "expected_periods": periods,
        "indicator_ids": indicators,
        "unit": "; ".join(str(u) for u in units) if units else None,
        "n_values": n_values,
        "gold_lineage": mode,
    }
    return ItemFields(item_id, computed, mode, problems)


def merge_fields(
    item: dict[str, Any], computed: ItemFields, overwrite: bool = False
) -> tuple[dict[str, Any], list[str]]:
    """Return the item with the computed fields set, and the differences kept unchanged.

    Hand-filled fields are added as `null` when absent and never changed. A script field that
    already holds a different value is kept unless `overwrite` is set; the difference is
    reported either way.
    """
    merged = dict(item)
    differences: list[str] = []
    for name in HAND_FIELDS:
        merged.setdefault(name, None)
    for name, value in computed.fields.items():
        current = merged.get(name)
        if current is None or current == [] or current == value:
            merged[name] = value
            continue
        differences.append(f"{computed.item_id}: {name} is {current!r}, computed {value!r}")
        if overwrite:
            merged[name] = value
    return merged, differences
