"""Graph adapters for T4's deterministic plan, SQL, derivation and check tools."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from analyst.agents.context import indicators_of
from analyst.agents.events import stage_event
from analyst.agents.state import AnalystState
from analyst.contracts import DerivedValue, InterpretationPlan, QueryIntent, UnresolvedSlot
from analyst.tools.calc import (
    cagr,
    change_pp,
    inflation_from_index,
    mean,
    pct_change,
    per_capita,
    share,
)
from analyst.tools.checks import NOT_IN_RESULT, run_result_checks, verify_numbers
from analyst.tools.codelists import codelist
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


_PREVIOUS_KEYS = ("from_period", "previous", "start", "from", "base", "start_period")
_CURRENT_KEYS = ("to_period", "current", "end", "to", "end_period")
_PERCENT_OPS = {"pct_change", "cagr", "share", "inflation_from_index"}
_PLACE_COLUMNS = ("geo_name", "geo_code")


def _value_column(state: AnalystState) -> int | None:
    """The numeric measure column: ``value`` when returned, else the only numeric column."""
    if state.result is None:
        raise ValueError("derivations need a plan and a result")
    names = [column.name for column in state.result.columns]
    if "value" in names:
        return names.index("value")
    numeric = [
        index
        for index, name in enumerate(names)
        if not name.endswith(("_id", "_code", "_label", "_name"))
        and any(
            isinstance(row[index], int | float) and not isinstance(row[index], bool)
            for row in state.result.rows
        )
    ]
    return numeric[0] if len(numeric) == 1 else None


def _aliases(state: AnalystState) -> dict[str, str]:
    """Map what the user wrote (and the resolved labels) to the labels found in the rows."""
    if state.plan is None:
        raise ValueError("derivations need a plan and a result")
    pairs: dict[str, str] = {}
    for period in state.plan.periods:
        pairs[period.requested.casefold()] = period.label.casefold()
        pairs[period.label.casefold()] = period.label.casefold()
    for place in state.plan.places:
        pairs[place.requested.casefold()] = place.name.casefold()
    return pairs


def _matching_rows(token: str, rows: list[int], state: AnalystState) -> list[int]:
    if state.result is None:
        raise ValueError("derivations need a plan and a result")
    target = _aliases(state).get(token.casefold(), token.casefold())
    return [
        index
        for index in rows
        if any(
            isinstance(cell, str) and cell.casefold() == target for cell in state.result.rows[index]
        )
    ]


def _first(args: dict[str, str], keys: tuple[str, ...]) -> str | None:
    return next((args[key] for key in keys if args.get(key)), None)


def _years_between(previous: str, current: str, state: AnalystState) -> int | None:
    if state.plan is None:
        raise ValueError("derivations need a plan and a result")
    starts = {}
    for period in state.plan.periods:
        starts[period.requested.casefold()] = period.start.year
        starts[period.label.casefold()] = period.start.year
    first, last = starts.get(previous.casefold()), starts.get(current.casefold())
    return last - first if first is not None and last is not None else None


def _derive_one(
    op: str, args: dict[str, str], state: AnalystState, first_id: int
) -> list[DerivedValue]:
    """Compute one requested derivation, once per place when the result covers several places.

    Inputs are named as the intent names them (``from_period``/``to_period``, ``part``/``total``)
    or as ``row:column`` cell references; each is mapped to exactly one result cell.
    """
    if state.result is None:
        raise ValueError("derivations need a plan and a result")
    result = state.result
    value_index = _value_column(state)
    names = [column.name for column in result.columns]
    place_index = next((names.index(c) for c in _PLACE_COLUMNS if c in names), None)
    groups: dict[str | None, list[int]] = {}
    for index, row in enumerate(result.rows):
        key = str(row[place_index]) if place_index is not None else None
        groups.setdefault(key, []).append(index)
    if not groups:
        groups[None] = []

    def failed(status: str, note: str, place: str | None = None) -> DerivedValue:
        return DerivedValue(
            id="",
            op=op,
            inputs=[],
            output=None,
            unit="",
            decimals=2,
            status=status,
            note=f"{place}: {note}" if place else note,
        )

    def cell(token: str, rows: list[int]) -> tuple[float, int, str]:
        if ":" in token and token.split(":", 1)[0].isdigit():
            number, row, column = _cell_ref(token, state)
            return float(number), row, column
        if value_index is None:
            raise LookupError("no single numeric value column in the result")
        matches = _matching_rows(token, rows, state)
        if len(matches) != 1:
            raise LookupError(f"{len(matches)} result rows match {token!r}")
        value = result.rows[matches[0]][value_index]
        if value is None or isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"the value for {token!r} is not reported")
        return float(value), matches[0], names[value_index]

    out: list[DerivedValue] = []
    for place, rows in groups.items():
        inputs: list[dict[str, Any]] = []
        try:
            if op in {"pct_change", "inflation_from_index", "change_pp", "difference", "cagr"}:
                previous, current = _first(args, _PREVIOUS_KEYS), _first(args, _CURRENT_KEYS)
                if previous is None or current is None:
                    raise KeyError("start and end inputs are not named")
                a, row_a, col_a = cell(previous, rows)
                b, row_b, col_b = cell(current, rows)
                inputs = [{"row": row_a, "column": col_a}, {"row": row_b, "column": col_b}]
                if op == "cagr":
                    periods = (
                        int(args["periods"])
                        if args.get("periods")
                        else _years_between(previous, current, state)
                    )
                    if not periods or periods <= 0:
                        raise KeyError("the number of years between the inputs is unknown")
                    output = cagr(a, b, periods)
                elif op in {"change_pp", "difference"}:
                    output = change_pp(b, a)
                else:
                    output = (pct_change if op == "pct_change" else inflation_from_index)(b, a)
            elif op == "share":
                part_token, total_token = args.get("part"), args.get("total")
                if not part_token or not total_token:
                    raise KeyError("part and total inputs are not named")
                part, row_p, col_p = cell(part_token, rows)
                total, row_t, col_t = cell(total_token, rows)
                inputs = [{"row": row_p, "column": col_p}, {"row": row_t, "column": col_t}]
                output = share(part, total)
            elif op == "per_capita":
                value, row_v, col_v = cell(args["value"], rows)
                population, row_n, col_n = cell(args["population"], rows)
                inputs = [{"row": row_v, "column": col_v}, {"row": row_n, "column": col_n}]
                output = per_capita(value, population, float(args.get("scale", "1")))
            elif op in {"mean", "weighted_mean"}:
                if value_index is None:
                    raise LookupError("no single numeric value column in the result")
                picked = [
                    i
                    for i in rows
                    if isinstance(result.rows[i][value_index], int | float)
                    and not isinstance(result.rows[i][value_index], bool)
                ]
                if len(picked) != len(rows):
                    raise ValueError("a value in the averaged rows is not reported")
                weights = None
                if op == "weighted_mean":
                    column = args.get("weights") or args.get("weight")
                    if not column or column not in names:
                        return [failed("incompatible_inputs", "no weight column in the result")]
                    weights = [float(result.rows[i][names.index(column)]) for i in picked]  # type: ignore[arg-type]
                inputs = [{"row": i, "column": names[value_index]} for i in picked]
                output = mean([float(result.rows[i][value_index]) for i in picked], weights)  # type: ignore[arg-type]
            else:
                raise ValueError(f"unsupported derivation: {op}")
        except (KeyError, LookupError) as error:
            # The query did not return the rows the derivation needs: a query fault.
            out.append(failed("input_unreported", f"{NOT_IN_RESULT}{error}", place))
            continue
        except (ValueError, TypeError, InvalidOperation) as error:
            out.append(failed("input_unreported", str(error), place))  # publisher did not report
            continue
        out.append(
            DerivedValue(
                id="",
                op=op,
                inputs=inputs,
                output=Decimal(str(output)) if output is not None else None,
                unit="percentage points"
                if op == "change_pp"
                else "percent"
                if op in _PERCENT_OPS
                else "",
                decimals=2,
                status="ok" if output is not None else "undefined",
                note=place,
            )
        )
    return [
        item.model_copy(update={"id": f"d{first_id + offset}"}) for offset, item in enumerate(out)
    ]


def _no_fit_plan(intent: QueryIntent) -> InterpretationPlan:
    """An empty plan on ``none_fit``; coverage reports it as not covered (design Section 5)."""
    return InterpretationPlan(
        dataset_id="none_fit",
        obs_table="obs_none_fit",
        dataset_version="none",
        indicators=[],
        places=[],
        all_places_level=None,
        periods=[],
        categories={},
        operation=intent.operation,
        order=None,
        limit=None,
        derivations=[],
        exclude_total_rows=True,
        assumptions=[],
        unresolved=[],
    )


def _missing_slot(
    intent: QueryIntent,
) -> Literal["place", "period", "indicator", "category", "geo_level"]:
    """The slot the intent names (prompt v2), else a guess from the empty mentions."""
    if intent.missing_slot is not None:
        return intent.missing_slot
    if not intent.period_mentions:
        return "period"
    if not intent.place_mentions and not intent.all_places_level:
        return "place"
    return "category"


def _descriptors(state: AnalystState, catalogue: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Definitional texts whose bare numbers describe the measure ("persons aged 15+")."""
    plan = state.plan
    if plan is None:
        return []
    texts = [f"{i.label} {i.unit}" for i in plan.indicators]
    texts += [p.name for p in plan.places] + [a.text for a in plan.assumptions]
    texts += [value for values in plan.categories.values() for value in values]
    table = catalogue.get(plan.dataset_id) or {}
    texts += [str(table.get(k, "")) for k in ("title", "source_name", "publisher", "source_table")]
    if state.evidence is not None:
        texts += [str(source.model_dump()) for source in state.evidence.sources]
    return texts


def _clarify_options(
    slot: str,
    intent: QueryIntent,
    table: Mapping[str, Any],
    deps: ToolNodeDependencies,
) -> list[str]:
    """Options a clarification can offer, decided by code from the table (at most 6).

    A missing group or category offers the table's own measure ("... persons aged 15+") and its
    category values; a missing period offers the latest published periods.
    """
    indicators = indicators_of(dict(table))
    chosen = [i for i in indicators if i["indicator_id"] in intent.indicator_ids] or (
        indicators if len(indicators) == 1 else []
    )
    if slot in {"category", "indicator"}:
        labels = [re.sub(r"(?<=[A-Za-z)%])\d+\b", "", str(i["label"])) for i in chosen]
        values = [
            v for column in (table.get("categories") or {}) for v in codelist_of(table, column)
        ]
        return list(dict.fromkeys([*labels, *values]))[:6]
    if slot == "period":
        db = deps.database_for(str(table["dataset_id"]))
        try:
            rows = db.execute(
                f"SELECT DISTINCT period_label, period_start FROM {table['obs_table']} "  # noqa: S608 - catalogue identifier
                "WHERE period_label IS NOT NULL ORDER BY period_start DESC LIMIT 6"
            ).fetchall()
        finally:
            db.close()
        return [str(r[0]) for r in rows]
    return []


def codelist_of(table: Mapping[str, Any], column: str) -> list[str]:
    values = codelist(str(table["dataset_id"]), column)
    return values if len(values) <= 6 else []


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
        if table is None or state.intent.action == "decline":
            # No listed table fits, or the intent declines: coverage reports it as not covered.
            plan = _no_fit_plan(state.intent)
            return {
                "plan": plan,
                "events": stage_event(
                    state, "resolve_places_periods_units", dataset_id=plan.dataset_id, unresolved=0
                ),
            }
        try:
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
        except Exception as error:  # a resolution fault ends the run as a backend error
            return {
                "node_error": "backend_error",
                "events": stage_event(
                    state,
                    "resolve_places_periods_units",
                    "failure",
                    error=type(error).__name__,
                    detail=str(error)[:300],
                ),
            }
        if state.intent.action == "clarify" and not plan.unresolved:
            # The intent asks for a detail the question leaves out; coverage turns an
            # unresolved slot into a clarification.
            plan = plan.model_copy(
                update={
                    "unresolved": [
                        UnresolvedSlot(
                            slot=_missing_slot(state.intent),
                            mention=state.intent.reason or "",
                            options=_clarify_options(
                                _missing_slot(state.intent), state.intent, table, deps
                            ),
                        )
                    ]
                }
            )
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
        for request in state.plan.derivations:
            if request.op == "rank":
                continue  # ordering is done by the query; there is no single derived value
            out.extend(_derive_one(request.op, request.args, state, first_id=len(out) + 1))
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
        report = verify_numbers(
            state.narration[-1].text, numeric, descriptors=_descriptors(state, deps.catalogue)
        )
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
