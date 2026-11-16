from __future__ import annotations
from typing import Any
from analyst.contracts.chart import ChartSpec

def select_chart(rows: list[dict[str, Any]], *, x: str | None = None,
                 y: str | None = None) -> ChartSpec:
    """Choose a safe chart type from verified tabular result rows."""
    if not rows:
        return ChartSpec(chart_type="table", specification={"reason": "empty_result"})
    columns = list(rows[0])
    x_key = x if x in columns else columns[0]
    numeric = [k for k in columns if any(isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool) for r in rows)]
    y_key = y if y in numeric else next((k for k in numeric if k != x_key), None)
    if y_key is None:
        return ChartSpec(chart_type="table", specification={"reason": "no_numeric_series"})
    if len(rows) <= 20:
        kind = "bar"
    else:
        kind = "line"
    return ChartSpec(chart_type=kind, specification=vega_lite_spec(rows, x_key, y_key, kind))

def vega_lite_spec(rows: list[dict[str, Any]], x: str, y: str, chart_type: str = "bar") -> dict[str, Any]:
    """Build a compact Vega-Lite spec; data is supplied only from verified result rows."""
    mark = "line" if chart_type == "line" else "bar"
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": rows},
        "mark": {"type": mark, "tooltip": True},
        "encoding": {
            "x": {"field": x, "type": "nominal", "sort": None},
            "y": {"field": y, "type": "quantitative"},
        },
    }
