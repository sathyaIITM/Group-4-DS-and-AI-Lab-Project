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


# Columns that never tell rows apart for a chart (identifiers, units, flags, provenance).
NOT_SPLIT = {
    "unit",
    "quality_flag",
    "geo_code",
    "geo_level",
    "period_type",
    "dataset_version",
    "source_row",
    "is_total_row",
    "geo_vintage",
    "rule_ids",
    "value_text",
}
INDICATOR_COLUMNS = ("indicator_label", "label", "indicator_id", "indicator")


def _split_column(
    result: QueryResult,
    period: str | None,
    entity: str | None,
    prefer: tuple[str, ...] = (),
) -> str | None:
    """The column that tells rows apart when place and period are the same: the plan's category
    columns first (area, sector, crop season ...), then the indicator columns, then any other
    text column with more than one value (UI test, 19 Nov: age groups, then area groups)."""
    if _distinct(result, entity) > 1 or _distinct(result, period) > 1:
        return None
    names = [c.name for c in result.columns]
    _, measure, _ = column_roles(result)
    others = [n for n in names if n not in NOT_SPLIT and n not in {measure, period, entity}]
    order = [*prefer, *INDICATOR_COLUMNS, *others]
    return next((c for c in order if c in names and _distinct(result, c) > 1), None)


def _points_are_unique(result: QueryResult, *columns: str | None) -> bool:
    """True when no two rows fall on the same chart position (Vega-Lite would stack them)."""
    names = [c.name for c in result.columns]
    index = [names.index(c) for c in columns if c is not None and c in names]
    keys = [tuple(row[i] for i in index) for row in result.rows]
    return len(set(keys)) == len(keys)


def _distinct(result: QueryResult, column: str | None) -> int:
    if column is None:
        return 0
    i = [c.name for c in result.columns].index(column)
    return len({row[i] for row in result.rows})


def _title_and_unit(plan: InterpretationPlan | None) -> tuple[str, str]:
    if plan is None or not plan.indicators:
        return "", ""
    if len(plan.indicators) > 1:  # several measures: no title; the unit when they share one
        units = {i.unit for i in plan.indicators}
        return "", units.pop() if len(units) == 1 else ""
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
        labels = (
            {i.indicator_id: re.sub(r"(?<=[A-Za-z)%])\d+\b", "", i.label) for i in plan.indicators}
            if plan
            else None
        )
        prefer = tuple(plan.categories) if plan else ()
        vega = (
            vega_lite_spec(result, kind, title, unit, labels, prefer)
            if result is not None
            else None
        )
        if vega is None and kind not in {"table_only", "single_value"}:
            # The rows cannot be drawn without stacking unrelated values: show the table.
            return ChartSpec(
                chart_type="table_only",
                decided_by=decided_by,
                reason="rows overlap on one chart position; shown as a table",
                vega_lite=None,
            )
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
    result: QueryResult,
    chart_type: ChartType,
    title: str = "",
    unit: str = "",
    labels: dict[str, str] | None = None,
    prefer: tuple[str, ...] = (),
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
    split = _split_column(result, period, entity, prefer)
    if split is not None and labels:
        values = [{**v, split: labels.get(str(v.get(split)), v.get(split))} for v in values]
    category = split or entity or period or next((n for n in names if n != measure), measure)
    coloured = entity if entity is not None and _distinct(result, entity) > 1 else None
    position = {
        "line": (period, coloured),
        "grouped_bar": (entity, period),
    }.get(chart_type, (category,))
    if not _points_are_unique(result, *position):
        return None  # two rows on one point would be stacked into a false total
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
