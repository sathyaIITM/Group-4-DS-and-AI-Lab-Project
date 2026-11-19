"""Chart selection and Vega-Lite specifications: column roles, time order, series, titles."""

from __future__ import annotations

from analyst.agents.stubs import stub_plan
from analyst.contracts import IndicatorRef
from analyst.contracts.results import QueryResult
from analyst.tools.charts import column_roles, select_chart


def _result(columns: list[str], rows: list[list[object]]) -> QueryResult:
    return QueryResult.model_validate(
        {
            "sql": "SELECT 1",
            "columns": [{"name": c, "type": "?"} for c in columns],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
            "dataset_versions": {},
            "exec_ms": 1,
        }
    )


def _plan(operation: str, label: str = "Unemployment rate3 (%)", unit: str = "percent"):
    return stub_plan("demo").model_copy(
        update={
            "operation": operation,
            "indicators": [IndicatorRef(indicator_id="ur", label=label, unit=unit)],
        }
    )


def test_trend_uses_the_period_axis_not_the_first_column() -> None:
    rows = [["Wheat", f"{y}-{(y + 1) % 100:02d}", 1000.0 + y] for y in range(2013, 2025)]
    spec = select_chart(_plan("trend"), _result(["entity", "period_label", "value"], rows))
    assert spec.chart_type == "line"
    enc = spec.vega_lite["encoding"]
    assert enc["x"] == {
        "field": "period_label",
        "type": "ordinal",
        "sort": "ascending",
        "title": None,
    }
    assert "color" not in enc  # one series


def test_several_places_become_several_lines() -> None:
    rows = [[p, y, 5.0] for p in ("Kerala", "Bihar") for y in ("2019-20", "2018-19", "2017-18")]
    spec = select_chart(_plan("trend"), _result(["geo_name", "period_label", "value"], rows))
    assert spec.vega_lite["encoding"]["color"]["field"] == "geo_name"


def test_change_for_several_places_is_a_grouped_bar() -> None:
    rows = [[p, y, 5.0] for p in ("Kerala", "Bihar") for y in ("2017-18", "2021-22")]
    spec = select_chart(_plan("change"), _result(["geo_name", "period_label", "value"], rows))
    assert spec.chart_type == "grouped_bar"
    assert spec.vega_lite["encoding"]["xOffset"]["field"] == "period_label"


def test_measure_is_value_and_identifiers_are_not_plotted() -> None:
    result = _result(["geo_code", "rank_id", "value", "year"], [["a", 1, 2.0, 2020]])
    assert column_roles(result) == ("year", "value", None)
    result = _result(["entity", "rank_id", "total"], [["a", 1, 2.0], ["b", 2, 3.0]])
    assert column_roles(result)[1] == "total"


def test_title_and_unit_come_from_the_plan() -> None:
    rows = [["Kerala", 9.6], ["Bihar", 5.9]]
    spec = select_chart(_plan("comparison"), _result(["entity", "value"], rows))
    assert spec.vega_lite["title"] == "Unemployment rate"
    assert spec.vega_lite["encoding"]["y"]["title"] == "percent"


def test_ranking_sorts_bars_by_value() -> None:
    rows = [[f"d{i}", float(i)] for i in range(6)]
    spec = select_chart(_plan("ranking"), _result(["entity", "value"], rows))
    assert spec.chart_type == "horizontal_bar_sorted"
    assert spec.vega_lite["encoding"]["y"]["sort"] == "-x"
