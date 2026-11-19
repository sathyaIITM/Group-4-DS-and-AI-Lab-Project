"""Query results and derived values (design document Section 4.4)."""

from decimal import Decimal
from typing import Literal

from analyst.contracts.common import CellRef, Contract
from analyst.contracts.intent import DerivationOp


class ColumnSpec(Contract):
    """Name and type of one result column."""

    name: str
    type: str


class QueryResult(Contract):
    """Rows returned by a read-only query, with the SQL, table versions and run time."""

    sql: str
    columns: list[ColumnSpec]
    rows: list[list[str | int | float | bool | None]]
    row_count: int
    truncated: bool
    dataset_versions: dict[str, str]
    exec_ms: int


class DerivedValue(Contract):
    """A value computed from result cells by a named operation, with its status."""

    id: str
    op: DerivationOp
    inputs: list[CellRef]
    output: Decimal | None
    unit: str
    decimals: int
    status: Literal["ok", "input_unreported", "undefined", "incompatible_inputs"]
    note: str | None
