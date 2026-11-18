"""Chart selection and Vega-Lite specifications (design document Section 6.7).

The chart is built from the executed result only: the rows are inlined in the specification and
no figure is added. Column roles are read from the result columns, not from their position:

- period: `period_label` (or `period_start`, `year`, `year_month`, `date`), drawn as an ordered
  axis in ascending order whatever the row order of the query;
- measure: `value` when returned, otherwise the only numeric column that is not an identifier;
- entity (place or item): `entity`, `geo_name`, `place`, `commodity_name`, `crop`, `geo_state`
  or `name`; several entities in a trend become several coloured lines.

Vega-Lite was chosen over Plotly (compared on 18 November on four real results): the
specification is plain data about 7 times smaller, it renders server-side to PNG or SVG
without a browser (`vl-convert`), and it embeds in either a Next.js or a Streamlit interface.
"""

from __future__ import annotations

import re
from typing import Any

from analyst.contracts import ChartSpec, ChartType, InterpretationPlan, QueryResult

MAX_CATEGORIES = 30
PERIOD_COLUMNS = ("period_label", "period_start", "year_month", "year", "date")
ENTITY_COLUMNS = ("entity", "geo_name", "place", "commodity_name", "crop", "geo_state", "name")
_ID_SUFFIXES = ("_id", "_code", "_rank")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _numeric(result: QueryResult) -> list[str]:
    names = [c.name for c in result.columns]
    return [name for i, name in enumerate(names) if any(_is_number(r[i]) for r in result.rows)]


def column_roles(result: QueryResult) -> tuple[str | None, str | None, str | None]:
    """(period, measure, entity) column names of a result; None where there is no such column."""
    names = [c.name for c in result.columns]
    period = next((c for c in PERIOD_COLUMNS if c in names), None)
    entity = next((c for c in ENTITY_COLUMNS if c in names), None)
    numeric = [n for n in _numeric(result) if n != period and not n.endswith(_ID_SUFFIXES)]
    if "value" in numeric:
        measure: str | None = "value"
    else:
        measure = numeric[0] if len(numeric) == 1 else (numeric[-1] if numeric else None)
    return period, measure, entity


def _distinct(result: QueryResult, column: str | None) -> int:
    if column is None:
        return 0
    i = [c.name for c in result.columns].index(column)
    return len({row[i] for row in result.rows})


def _title_and_unit(plan: InterpretationPlan | None) -> tuple[str, str]:
    if plan is None or len(plan.indicators) != 1:
        return "", ""
    indicator = plan.indicators[0]
    label = re.sub(r"(?<=[A-Za-z)%])\d+\b", "", indicator.label)  # footnote markers
    label = re.sub(r"\s*\((?:%|Rs\.?|per cent)\)\s*$", "", label).strip()
    return label, indicator.unit


def select_chart(
    plan: InterpretationPlan | None, result: QueryResult | None, user_request: str | None = None
) -> ChartSpec:
    """Choose the chart type by the rules of Section 6.7; values come from the result only."""
    title, unit = _title_and_unit(plan)

    def spec(kind: ChartType, reason: str, decided_by: str = "rules") -> ChartSpec:
        vega = vega_lite_spec(result, kind, title, unit) if result is not None else None
        return ChartSpec(chart_type=kind, decided_by=decided_by, reason=reason, vega_lite=vega)

    if result is None or result.row_count == 0:
        return spec("table_only", "no rows")
    period, measure, entity = column_roles(result)
    if measure is None:
        return spec("table_only", "no numeric column")
    units = {i.unit for i in plan.indicators} if plan else set()
    if result.row_count > MAX_CATEGORIES * 4 or len(units) > 1:
        return spec("table_only", "too many rows for a chart, or mixed units")
    operation = plan.operation if plan else "lookup"
    if result.row_count == 1:
        return spec("single_value", "one value")
    periods, entities = _distinct(result, period), _distinct(result, entity)
    if operation == "trend" and periods > 2:
        return spec("line", "trend over more than 2 periods")
    if periods > 2 and entities <= 5 and operation not in {"ranking", "comparison"}:
        return spec("line", "values over more than 2 periods")
    if result.row_count > MAX_CATEGORIES:
        return spec("table_only", "more than 30 categories")
    if operation == "ranking" and result.row_count > 3:
        return spec("horizontal_bar_sorted", "ranking with more than 3 rows")
    if periods >= 2 and entities >= 2:
        return spec("grouped_bar", "several places over two or more periods")
    if operation == "change" and entities <= 1:
        return spec("single_value", "change for one place")
    return spec("bar", "comparison of more than one value")


def vega_lite_spec(
    result: QueryResult, chart_type: ChartType, title: str = "", unit: str = ""
) -> dict[str, Any] | None:
    """A Vega-Lite v5 specification with data inlined from the stored rows; None for a table."""
    if chart_type in {"table_only", "single_value"}:
        return None
    period, measure, entity = column_roles(result)
    if measure is None:
        return None
    names = [c.name for c in result.columns]
    values = [dict(zip(names, row, strict=True)) for row in result.rows]
    y = {"field": measure, "type": "quantitative", "title": unit or measure}
    category = entity or period or next((n for n in names if n != measure), measure)
    if chart_type == "line" and period is not None:
        encoding: dict[str, Any] = {
            "x": {"field": period, "type": "ordinal", "sort": "ascending", "title": None},
            "y": y,
        }
        if entity is not None and _distinct(result, entity) > 1:
            encoding["color"] = {"field": entity, "type": "nominal", "title": None}
        mark: dict[str, Any] = {"type": "line", "point": True, "tooltip": True}
    elif chart_type == "horizontal_bar_sorted":
        encoding = {
            "y": {"field": category, "type": "nominal", "sort": "-x", "title": None},
            "x": y,
        }
        mark = {"type": "bar", "tooltip": True}
    elif chart_type == "grouped_bar" and entity is not None and period is not None:
        encoding = {
            "x": {"field": entity, "type": "nominal", "title": None},
            "xOffset": {"field": period, "sort": "ascending"},
            "color": {"field": period, "type": "ordinal", "sort": "ascending", "title": None},
            "y": y,
        }
        mark = {"type": "bar", "tooltip": True}
    else:
        encoding = {
            "x": {"field": category, "type": "nominal", "sort": None, "title": None},
            "y": y,
        }
        mark = {"type": "bar", "tooltip": True}
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "data": {"values": values},
        "mark": mark,
        "encoding": encoding,
    }
