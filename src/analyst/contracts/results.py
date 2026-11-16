from pydantic import Field
from .common import Contract
class QueryResult(Contract):
    rows: tuple[dict[str, object], ...] = ()
    schema_: tuple[dict[str, str], ...] = Field(default=(), alias="schema")
    dataset_version: str | None = None
    elapsed_ms: float = 0.0
class DerivedValue(Contract):
    operation: str = ""
    inputs: tuple[str, ...] = ()
    output: float | None = None
    unit: str | None = None
    rounding: str | None = None
    status: str = "ok"
