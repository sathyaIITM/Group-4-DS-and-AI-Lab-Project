"""Graph adapters for T4's deterministic plan, SQL, derivation and check tools."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from analyst.agents.context import indicators_of
from analyst.agents.events import stage_event
from analyst.agents.state import AnalystState
from analyst.contracts import DerivedValue
from analyst.tools.calc import (
    cagr,
    change_pp,
    inflation_from_index,
    mean,
    pct_change,
    per_capita,
    share,
)
from analyst.tools.checks import run_result_checks, verify_numbers
from analyst.tools.resolve import resolve_plan
from analyst.tools.sql_runner import ReadOnlyDatabase, SqlRejectedError, SqlTimeoutError, check_sql

NodeFn = Callable[[AnalystState], dict[str, Any]]


@dataclass(frozen=True)
class ToolNodeDependencies:
    catalogue: Mapping[str, Mapping[str, Any]]
    refs: Mapping[str, Any]
    database_for: Callable[[str], ReadOnlyDatabase]


def _error_class(error: Exception) -> str:
    message = str(error).casefold()
    if "column" in message or "binder" in message:
        return "unknown_column"
    if "table function" in message or "read_csv" in message or "read_parquet" in message:
        return "table_function"
    if "table not in catalogue" in message:
        return "unregistered_table"
    if "parse" in message or "syntax" in message:
        return "parse"
    return "execution"


def _cell_ref(token: str, state: AnalystState) -> tuple[Decimal, int, str]:
    row_text, separator, column = token.partition(":")
    if not separator or state.result is None:
        raise ValueError(f"cell reference must be row:column: {token!r}")
    row_index = int(row_text)
    column_index = next(
        (i for i, spec in enumerate(state.result.columns) if spec.name == column), -1
    )
    if not 0 <= row_index < len(state.result.rows) or column_index < 0:
        raise ValueError(f"cell reference is outside result: {token!r}")
    value = state.result.rows[row_index][column_index]
    if value is None or isinstance(value, bool):
        raise ValueError(f"cell reference is not numeric: {token!r}")
    return Decimal(str(value)), row_index, column


def make_tool_nodes(deps: ToolNodeDependencies) -> dict[str, NodeFn]:
    """Return graph node overrides; callers combine these with the T2 and T3 adapters."""

    def resolve(state: AnalystState) -> dict[str, Any]:
        if state.intent is None:
            return {
                "node_error": "backend_error",
                "events": stage_event(
                    state, "resolve_places_periods_units", "failure", detail="no parsed intent"
                ),
            }
        table = deps.catalogue.get(state.intent.dataset_id)
        if table is None:
            return {
                "node_error": "backend_error",
                "events": stage_event(
                    state,
                    "resolve_places_periods_units",
                    "failure",
                    detail="dataset missing from published catalogue",
                ),
            }
        db = deps.database_for(state.intent.dataset_id)
        try:
            plan = resolve_plan(
                state.intent,
                dataset=table,
                indicators=indicators_of(dict(table)),
                db=db,
                refs=deps.refs,
                catalogue=deps.catalogue,
            )
        finally:
            db.close()
        return {
            "plan": plan,
            "events": stage_event(
                state, "resolve_places_periods_units", unresolved=len(plan.unresolved)
            ),
        }

    def validate_sql(state: AnalystState) -> dict[str, Any]:
        if state.plan is None or not state.sql:
            return {
                "validation_result": "invalid",
                "events": stage_event(
                    state, "validate_sql_with_sqlglot", "failure", detail="missing plan or SQL"
                ),
            }
        attempt = state.sql[-1]
        try:
            db = deps.database_for(state.plan.dataset_id)
            try:
                check_sql(attempt.sql, db.table_names)
                db.check_columns(attempt.sql)
            finally:
                db.close()
        except (SqlRejectedError, ValueError) as error:
            updated = attempt.model_copy(
                update={"valid": False, "error_class": _error_class(error), "error": str(error)}
            )
            return {
                "sql": [updated],
                "validation_result": "invalid",
                "events": stage_event(
                    state, "validate_sql_with_sqlglot", "failure", error_class=updated.error_class
                ),
            }
        updated = attempt.model_copy(update={"valid": True, "error_class": "none", "error": None})
        return {
            "sql": [updated],
            "validation_result": "valid",
            "events": stage_event(state, "validate_sql_with_sqlglot", status="valid"),
        }

    def execute_sql(state: AnalystState) -> dict[str, Any]:
        if state.plan is None or not state.sql:
            return {
                "execution_result": "error",
                "events": stage_event(
                    state, "execute_read_only_duckdb", "failure", detail="missing plan or SQL"
                ),
            }
        started = time.perf_counter()
        attempt = state.sql[-1]
        try:
            db = deps.database_for(state.plan.dataset_id)
            try:
                names, rows = db.run(attempt.sql)
                types = dict(db.describe(state.plan.obs_table))
            finally:
                db.close()
            columns = [{"name": name, "type": types.get(name, "derived")} for name in names]
            elapsed = round((time.perf_counter() - started) * 1000)
            result = {
                "sql": attempt.sql,
                "columns": columns,
                "rows": [list(row) for row in rows],
                "row_count": len(rows),
                "truncated": len(rows) >= 1000,
                "dataset_versions": {state.plan.dataset_id: state.plan.dataset_version},
                "exec_ms": elapsed,
            }
            updated_attempt = attempt.model_copy(update={"executed_ms": elapsed})
            return {
                "result": result,
                "sql": [updated_attempt],
                "execution_result": "success",
                "events": stage_event(
                    state,
                    "execute_read_only_duckdb",
                    status="success",
                    row_count=len(rows),
                    duration_ms=elapsed,
                ),
            }
        except Exception as error:
            updated_attempt = attempt.model_copy(
                update={
                    "error": str(error),
                    "error_class": "timeout" if isinstance(error, SqlTimeoutError) else "execution",
                }
            )
            return {
                "sql": [updated_attempt],
                "execution_result": "error",
                "events": stage_event(
                    state,
                    "execute_read_only_duckdb",
                    "failure",
                    error=type(error).__name__,
                    detail=str(error),
                ),
            }

    def derive(state: AnalystState) -> dict[str, Any]:
        if state.plan is None or state.result is None:
            return {
                "derived": [],
                "events": stage_event(
                    state, "compute_derivations", "failure", detail="missing plan or result"
                ),
            }
        out: list[DerivedValue] = []
        for index, request in enumerate(state.plan.derivations):
            try:
                args = request.args
                inputs: list[dict[str, Any]] = []
                values: dict[str, Decimal] = {}
                for key, token in args.items():
                    if ":" in token:
                        value, row, column = _cell_ref(token, state)
                        values[key] = value
                        inputs.append({"row": row, "column": column})
                op = request.op
                if op in {"pct_change", "inflation_from_index"}:
                    result = (pct_change if op == "pct_change" else inflation_from_index)(
                        values["current"], values["previous"]
                    )
                elif op == "change_pp":
                    result = change_pp(values["current"], values["previous"])
                elif op == "share":
                    result = share(values["part"], values["total"])
                elif op == "per_capita":
                    result = per_capita(
                        values["value"], values["population"], float(args.get("scale", "1"))
                    )
                elif op == "cagr":
                    result = cagr(values["start"], values["end"], int(args["periods"]))
                elif op in {"mean", "weighted_mean"}:
                    result = mean(list(values.values()))
                else:
                    raise ValueError(f"unsupported derivation: {op}")
                out.append(
                    DerivedValue(
                        id=f"d{index + 1}",
                        op=op,
                        inputs=inputs,
                        output=Decimal(str(result)) if result is not None else None,
                        unit="percent"
                        if op in {"pct_change", "cagr", "share", "inflation_from_index"}
                        else "",
                        decimals=2,
                        status="ok" if result is not None else "undefined",
                        note=None,
                    )
                )
            except (KeyError, ValueError, InvalidOperation, TypeError) as error:
                out.append(
                    DerivedValue(
                        id=f"d{index + 1}",
                        op=request.op,
                        inputs=[],
                        output=None,
                        unit="",
                        decimals=2,
                        status="input_unreported",
                        note=str(error),
                    )
                )
        return {"derived": out, "events": stage_event(state, "compute_derivations", count=len(out))}

    def result_checks(state: AnalystState) -> dict[str, Any]:
        if state.plan is None or state.result is None:
            return {
                "events": stage_event(
                    state, "deterministic_result_checks", "failure", detail="missing plan or result"
                )
            }
        report = run_result_checks(
            state.plan, state.result, [item.model_dump() for item in state.derived]
        )
        return {
            "checks": report,
            "events": stage_event(state, "deterministic_result_checks", verdict=report.verdict),
        }

    def number_check(state: AnalystState) -> dict[str, Any]:
        if not state.narration or state.result is None:
            return {
                "events": stage_event(
                    state,
                    "verify_numbers_deterministically",
                    "failure",
                    detail="missing narration or result",
                )
            }
        numeric: list[Any] = [
            value
            for row in state.result.rows
            for value in row
            if isinstance(value, int | float) and not isinstance(value, bool)
        ]
        numeric.extend(item.output for item in state.derived if item.output is not None)
        report = verify_numbers(state.narration[-1].text, numeric)
        return {
            "number_check": report,
            "events": stage_event(
                state,
                "verify_numbers_deterministically",
                passed=report.passed,
                unmatched=len(report.unmatched),
            ),
        }

    return {
        "resolve_places_periods_units": resolve,
        "validate_sql_with_sqlglot": validate_sql,
        "execute_read_only_duckdb": execute_sql,
        "compute_derivations": derive,
        "deterministic_result_checks": result_checks,
        "verify_numbers_deterministically": number_check,
    }
