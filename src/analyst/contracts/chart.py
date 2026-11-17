"""Chart specification (design document Section 4.7)."""

from typing import Any, Literal

from analyst.contracts.common import Contract

ChartType = Literal[
    "table_only", "single_value", "bar", "horizontal_bar_sorted", "line", "grouped_bar"
]


class ChartSpec(Contract):
    chart_type: ChartType
    decided_by: Literal["rules", "user", "jev"]
    reason: str
    vega_lite: dict[str, Any] | None
