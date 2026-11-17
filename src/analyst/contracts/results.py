"""Query results and derived values (design document Section 4.4)."""

from decimal import Decimal
from typing import Literal

from analyst.contracts.common import CellRef, Contract
from analyst.contracts.intent import DerivationOp


class ColumnSpec(Contract):
    name: str
    type: str


class QueryResult(Contract):
    sql: str
    columns: list[ColumnSpec]
    rows: list[list[str | int | float | bool | None]]
    row_count: int
    truncated: bool
    dataset_versions: dict[str, str]
    exec_ms: int


class DerivedValue(Contract):
    id: str
    op: DerivationOp
    inputs: list[CellRef]
    output: Decimal | None
    unit: str
    decimals: int
    status: Literal["ok", "input_unreported", "undefined", "incompatible_inputs"]
    note: str | None
