"""SQL drafts and attempts (design document Section 4.4)."""

from typing import Literal

from analyst.contracts.common import Contract


class SqlDraft(Contract):
    sql: str
    statement: str


class SqlAttempt(Contract):
    attempt: int
    kind: Literal["generate", "repair", "regenerate"]
    sql: str
    statement: str
    valid: bool
    error_class: Literal[
        "none",
        "parse",
        "not_select",
        "unregistered_table",
        "table_function",
        "unknown_column",
        "timeout",
        "execution",
    ] = "none"
    error: str | None
    executed_ms: int | None
