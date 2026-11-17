"""Chart selection and Vega-Lite specifications (design document Section 6.7)."""

from __future__ import annotations

from typing import Any

from analyst.contracts import ChartSpec, ChartType, InterpretationPlan, QueryResult

MAX_CATEGORIES = 30


def _numeric(result: QueryResult) -> list[str]:
    names = [c.name for c in result.columns]
    return [
        name
        for i, name in enumerate(names)
        if any(isinstance(r[i], int | float) and not isinstance(r[i], bool) for r in result.rows)
    ]


def select_chart(
    plan: InterpretationPlan | None, result: QueryResult | None, user_request: str | None = None
) -> ChartSpec:
    """Choose the chart type by the rules of Section 6.7; values come from the result only."""

    def spec(kind: ChartType, reason: str, decided_by: str = "rules") -> ChartSpec:
        vega = vega_lite_spec(result, kind) if result is not None else None
        return ChartSpec(
            chart_type=kind,
            decided_by=decided_by,
            reason=reason,
            vega_lite=vega,
        )

    if result is None or result.row_count == 0:
        return spec("table_only", "no rows")
    if not _numeric(result):
        return spec("table_only", "no numeric column")
    units = {i.unit for i in plan.indicators} if plan else set()
    if result.row_count > MAX_CATEGORIES or len(units) > 1:
        return spec("table_only", "more than 30 categories or mixed units")
    operation = plan.operation if plan else "lookup"
    if result.row_count == 1:
        return spec("single_value", "one value")
    if operation == "ranking" and result.row_count > 3:
        return spec("horizontal_bar_sorted", "ranking with more than 3 rows")
    if operation == "change":
        places = len(plan.places) if plan else 1
        if places <= 1:
            return spec("single_value", "change for one place")
        return spec("grouped_bar", "change for several places")
    if operation == "trend" and result.row_count > 2:
        return spec("line", "trend over more than 2 periods")
    return spec("bar", "comparison of more than one value")


def vega_lite_spec(
    result: QueryResult, chart_type: ChartType, title: str = "", unit: str = ""
) -> dict[str, Any] | None:
    """A Vega-Lite v5 specification with data inlined from the stored rows; None for a table."""
    if chart_type in {"table_only", "single_value"}:
        return None
    names = [c.name for c in result.columns]
    numeric = _numeric(result)
    y = numeric[-1]
    x = next((n for n in names if n != y), y)
    values = [dict(zip(names, row, strict=True)) for row in result.rows]
    mark = "line" if chart_type == "line" else "bar"
    encoding: dict[str, Any] = {
        "x": {"field": x, "type": "nominal", "sort": None},
        "y": {"field": y, "type": "quantitative", "title": unit or y},
    }
    if chart_type == "horizontal_bar_sorted":
        encoding = {
            "y": {"field": x, "type": "nominal", "sort": "-x"},
            "x": {"field": y, "type": "quantitative", "title": unit or y},
        }
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "data": {"values": values},
        "mark": {"type": mark, "tooltip": True},
        "encoding": encoding,
    }
