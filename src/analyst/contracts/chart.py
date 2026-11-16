from pydantic import Field
from .common import Contract
class ChartSpec(Contract):
    chart_type: str = "table"
    specification: dict[str, object] = Field(default_factory=dict)
