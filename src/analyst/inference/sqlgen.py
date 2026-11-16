"""`generate_sql_with_hosted_llm` and `bounded_sql_repair` (design document Section 5, Phase D).

The LLM writes one SELECT over the plan's `obs_<dataset>` table. A light check rejects replies
that are not a single SELECT on that table (and retries once); full validation (sqlglot,
registered tables, columns) is the next node's job.
"""

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from analyst.contracts.plan import InterpretationPlan
from analyst.contracts.sql import SqlDraft
from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient

_TABLE = re.compile(r"\bobs_[a-z0-9_]+\b", re.IGNORECASE)


def check_draft(draft: SqlDraft, obs_table: str) -> None:
    sql = draft.sql.strip()
    if not re.match(r"^(select|with)\b", sql, re.IGNORECASE):
        raise ValueError("the query must be one SELECT statement")
    if ";" in sql.rstrip(";"):
        raise ValueError("the query must be a single statement")
    tables = {t.lower() for t in _TABLE.findall(sql)}
    if tables != {obs_table.lower()}:
        raise ValueError(f"the query must read {obs_table} only, found {sorted(tables)}")
    if not draft.statement.strip():
        raise ValueError("statement is empty")


def _as_json(value: Any) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def generate_sql(
    plan: InterpretationPlan,
    schemas: Mapping[str, Any] | str,
    retrieved: Mapping[str, Any],
    prior_sql: str | None,
    hints: list[str] | None,
    llm: LlmClient,
    counters: CallCounter,
    regenerate: bool = False,
) -> tuple[SqlDraft, LlmCallRecord]:
    """`regenerate=True` after a failed result check: the thinking level for regeneration
    (`configs/model.yaml`, `thinking.on_regenerate.sql`) is used."""
    context = {
        "guidance": list(retrieved.get("cards", [])),
        "verified_examples": list(retrieved.get("examples", [])),
    }
    draft, record = llm.structured(
        "sql",
        "sql",
        {
            "plan": _as_json(plan),
            "schema": schemas,
            "context": context,
            "prior_sql": prior_sql,
            "hints": hints or None,
        },
        SqlDraft,
        counters=counters,
        validate=lambda d: check_draft(d, plan.obs_table),
        node="generate_sql_with_hosted_llm",
        regenerate=regenerate,
    )
    return draft.model_copy(update={"sql": draft.sql.strip().rstrip(";")}), record


def repair_sql(
    draft: SqlDraft,
    error: str,
    schemas: Mapping[str, Any] | str,
    obs_table: str,
    llm: LlmClient,
    counters: CallCounter,
) -> tuple[SqlDraft, LlmCallRecord]:
    repaired, record = llm.structured(
        "sql_repair",
        "sql_repair",
        {"sql": draft.sql, "statement": draft.statement, "error": error, "schema": schemas},
        SqlDraft,
        counters=counters,
        validate=lambda d: check_draft(d, obs_table),
        node="bounded_sql_repair",
    )
    return repaired.model_copy(update={"sql": repaired.sql.strip().rstrip(";")}), record
