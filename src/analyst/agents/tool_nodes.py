"""Graph adapters for the deterministic plan, SQL, derivation and check tools."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, get_args

from analyst.agents.context import indicators_of
from analyst.agents.events import stage_event
from analyst.agents.state import AnalystState
from analyst.contracts import (
    Assumption,
    DerivedValue,
    InterpretationPlan,
    QueryIntent,
    UnresolvedSlot,
)
from analyst.contracts.common import PeriodType
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
from analyst.tools.periods import is_now_mention, now_phrase
from analyst.tools.resolve import resolve_plan, total_value
from analyst.tools.sql_runner import ReadOnlyDatabase, SqlRejectedError, SqlTimeoutError, check_sql

NodeFn = Callable[[AnalystState], dict[str, Any]]


LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolNodeDependencies:
    """Catalogue, reference data and database access the tool nodes need."""

    catalogue: Mapping[str, Mapping[str, Any]]
    refs: Mapping[str, Any]
    database_for: Callable[[str], ReadOnlyDatabase]


def _error_class(error: Exception) -> str:
    """Classify a DuckDB error message into an SQL error class."""
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
    """Read a row:column reference and return the cell value, row and column."""
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
    """Return the result rows whose place or category matches a token."""
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
    """Return the first non-empty argument among the given keys."""
    return next((args[key] for key in keys if args.get(key)), None)


def _years_between(previous: str, current: str, state: AnalystState) -> int | None:
    """Return the number of years between two period labels of the plan."""
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
        """Return a derived value that failed with a status and note."""
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
        """Return the value, row and column a derivation argument refers to."""
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
                value_a, row_a, col_a = cell(previous, rows)
                value_b, row_b, col_b = cell(current, rows)
                inputs = [{"row": row_a, "column": col_a}, {"row": row_b, "column": col_b}]
                if op == "cagr":
                    periods = (
                        int(args["periods"])
                        if args.get("periods")
                        else _years_between(previous, current, state)
                    )
                    if not periods or periods <= 0:
                        raise KeyError("the number of years between the inputs is unknown")
                    output = cagr(value_a, value_b, periods)
                elif op in {"change_pp", "difference"}:
                    output = change_pp(value_b, value_a)
                else:
                    output = (pct_change if op == "pct_change" else inflation_from_index)(
                        value_b, value_a
                    )
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


PERIOD_TYPE_NAMES = set(get_args(PeriodType))


def _period_options(
    plan: InterpretationPlan,
    intent: QueryIntent,
    table: Mapping[str, Any],
    deps: ToolNodeDependencies,
) -> InterpretationPlan:
    """An unresolved period offers the table's latest periods, not its period-type names
    ("Options: month" in the jev_routing smoke test of 18 Nov)."""
    slots = [
        slot.model_copy(update={"options": _clarify_options("period", intent, table, deps)})
        if slot.slot == "period" and set(slot.options) <= PERIOD_TYPE_NAMES
        else slot
        for slot in plan.unresolved
    ]
    return plan.model_copy(update={"unresolved": slots}) if slots != plan.unresolved else plan


SINGLE_PLACE_OPERATIONS = {"lookup", "change", "trend", "share"}
# Units whose values add up across places (a sum over all districts is a national total); a
# rainfall depth, a price or a rate does not, so an aggregate of it needs a place.
ADDITIVE_UNITS = {
    "tonne", "hectare", "bale_170kg", "bale_180kg", "count", "lakh", "mixed_nuts_or_tonne",
}  # fmt: skip


def _needs_one_place(plan: InterpretationPlan, table: Mapping[str, Any]) -> bool:
    """A lookup, change, trend or share is about one place; so is an aggregate of a measure
    that does not add up across places ("total rainfall in 2015" on the sub-division table)."""
    if plan.operation in SINGLE_PLACE_OPERATIONS:
        return True
    units = table.get("indicator_units") or {}
    return plan.operation == "aggregate" and any(
        units.get(i.indicator_id) not in ADDITIVE_UNITS for i in plan.indicators
    )


def _missing_place(
    plan: InterpretationPlan, intent: QueryIntent, table: Mapping[str, Any]
) -> InterpretationPlan:
    """A question about one place that names none, on a table without a national row, is
    asked: there is no default place (e2e_v1 rule for tables without an all-India row; smoke
    run, 19 Nov: "the modal price of onion" listed a few of 482 markets). A ranking or a
    comparison across places needs no place, and a follow-up keeps the previous one."""
    if (
        intent.action != "answer"
        or plan.places
        or plan.all_places_level
        or plan.unresolved
        or not _needs_one_place(plan, table)
        or "national" in (table.get("geo_levels") or [])
    ):
        return plan
    slot = UnresolvedSlot(slot="place", mention="no place was named", options=[])
    return plan.model_copy(update={"unresolved": [slot]})


# Rule sheet S1: with several details missing, the first in this order is asked. The measure is
# settled before where and when (for a Mandi price, the commodity before the market).
SLOT_ORDER = ("indicator", "category", "place", "period", "geo_level")
# Category columns that define the measure itself: a price or a production figure means
# nothing without its commodity or crop, and no total value exists to default to.
MEASURE_COLUMNS = ("commodity_name", "crop")
MEASURE_FREE_OPERATIONS = {"ranking", "list"}
SINGLE_CROP_UNITS = {"bale_170kg", "bale_180kg", "mixed_nuts_or_tonne"}  # cotton, jute, coconut


def _missing_measure_category(
    plan: InterpretationPlan, intent: QueryIntent, table: Mapping[str, Any]
) -> InterpretationPlan:
    """A price or production question that names no commodity or crop is asked for it, before
    any missing place (rule sheet S1; Milestone 4 error analysis: the market was asked first).
    A ranking or list across commodities needs none, and a follow-up keeps the previous one."""
    if (
        intent.action != "answer"
        or plan.unresolved
        or plan.operation in MEASURE_FREE_OPERATIONS
        or intent.changed_slots
    ):
        return plan
    units = table.get("indicator_units") or {}
    if plan.indicators and all(
        units.get(i.indicator_id) in SINGLE_CROP_UNITS for i in plan.indicators
    ):
        return plan
    dataset_id = str(table.get("dataset_id"))
    for column in MEASURE_COLUMNS:
        if column not in (table.get("categories") or {}) or plan.categories.get(column):
            continue
        if total_value(dataset_id, column) is not None:
            continue
        slot = UnresolvedSlot(
            slot="category",
            mention=f"{column} was not named",
            options=codelist_of(table, column),
        )
        return plan.model_copy(update={"unresolved": [slot]})
    return plan


def _order_slots(plan: InterpretationPlan) -> InterpretationPlan:
    """Unresolved slots in the order of rule S1, so the first one asked is the measure."""
    ordered = sorted(plan.unresolved, key=lambda s: SLOT_ORDER.index(s.slot))
    return plan.model_copy(update={"unresolved": ordered}) if ordered != plan.unresolved else plan


def _rainfall(table: Mapping[str, Any]) -> bool:
    """A weather table: "right now" there asks for today's conditions, which no table holds."""
    return str(table.get("domain") or "") == "rainfall" or "rainfall" in str(
        table.get("dataset_id") or ""
    )


def review_intent(
    intent: QueryIntent, table: Mapping[str, Any] | None, question: str
) -> QueryIntent:
    """Correct two decline intents that the rule sheet says are not declines, when a listed
    table holds the measure:

    - a group or definition the table lacks ("youth" on a persons-15+ table) is `clarify`,
      slot `category`, offering the table's own group (rule E9; guide R12);
    - "now", "currently", "latest" on a statistical table ask for the latest published period,
      stated (rule D1b). Only today's weather and forecasts stay declined (rule E6).
    """
    if intent.action != "decline" or table is None:
        return intent
    if intent.missing_slot == "category":
        return intent.model_copy(update={"action": "clarify"})
    if intent.missing_slot == "period" and not _rainfall(table):
        mentions = list(intent.period_mentions)
        phrase = now_phrase(question)
        if (mentions and all(is_now_mention(m) for m in mentions)) or (not mentions and phrase):
            return intent.model_copy(
                update={
                    "action": "answer",
                    "missing_slot": None,
                    "reason": None,
                    "period_mentions": mentions or [phrase],
                }
            )
    return intent


MAX_CATEGORY_OPTIONS = 6


def _ambiguous_category(
    plan: InterpretationPlan,
    intent: QueryIntent,
    table: Mapping[str, Any],
    deps: ToolNodeDependencies,
) -> InterpretationPlan:
    """A single-value question whose rows would differ in a category the user did not name,
    and that has no total value to default to, is asked, offering the values found (MSP of
    paddy: Common or Grade A; smoke run, 19 Nov, where one variety or both were reported)."""
    if (
        intent.action != "answer"
        or plan.unresolved
        or plan.operation != "lookup"
        or len(plan.places) > 1
        or len(plan.periods) != 1
        or not plan.indicators
    ):
        return plan
    dataset_id = str(table.get("dataset_id"))
    obs = str(table.get("obs_table") or f"obs_{dataset_id}")
    if not re.fullmatch(r"obs_[a-z][a-z0-9_]*", obs):
        return plan
    window = plan.periods[0]
    for column in table.get("categories") or {}:
        if column in plan.categories or total_value(dataset_id, column) is not None:
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]*", column):
            continue
        ids = [i.indicator_id for i in plan.indicators]
        where = [
            f"indicator_id IN ({', '.join('?' for _ in ids)})",
            "period_start = ?",
            "period_end = ?",
            "quality_flag <> 'implausible'",
        ]
        params: list[Any] = [*ids, window.start, window.end]
        for name, values in plan.categories.items():
            if re.fullmatch(r"[a-z][a-z0-9_]*", name) and values:
                where.append(f"{name} IN ({', '.join('?' for _ in values)})")
                params.extend(values)
        if plan.places:
            where.append("geo_code = ?")
            params.append(plan.places[0].code)
        db = deps.database_for(dataset_id)
        try:
            found = db.execute(
                f"SELECT DISTINCT {column} FROM {obs} WHERE {' AND '.join(where)} "  # noqa: S608 - validated identifiers
                f"AND {column} IS NOT NULL ORDER BY 1 LIMIT 7",
                params,
            ).fetchall()
        except Exception as error:  # a lookup that cannot be checked is left to the checks
            LOG.warning("category check on %s.%s skipped: %s", dataset_id, column, error)
            continue
        finally:
            db.close()
        values = [str(row[0]) for row in found]
        # Asked only for a small closed set (MSP varieties, crop seasons); a long open list such
        # as market varieties is answered across all values.
        if 1 < len(values) <= MAX_CATEGORY_OPTIONS:
            slot = UnresolvedSlot(
                slot="category", mention=f"{column} was not named", options=values[:6]
            )
            return plan.model_copy(update={"unresolved": [slot]})
    return plan


def _single_measure(slot: str, options: list[str], plan: InterpretationPlan) -> bool:
    """A clarification about the measure with one option, which the plan already resolved.
    Indicator slot only: a missing group ("youth" on a persons-15+ table, slot `category`) must
    be asked, never answered with the one group the table has."""
    if slot != "indicator" or len(options) != 1 or len(plan.indicators) != 1:
        return False
    label = re.sub(r"(?<=[A-Za-z)%])\d+\b", "", plan.indicators[0].label)
    return options[0] == label


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
        if len(labels) > 1:
            # The intent named the candidate groups (age groups as NFHS indicators): offer only
            # those, not the table's area values as well (UI test, 19 Nov).
            return labels[:6]
        # A column with a total value (area: Total) is defaulted by code, so it is not a missing
        # choice; offering its values next to a population group mixed two questions (UI test,
        # 19 Nov: "youth" offered "Women 15-19; Rural; Total; Urban").
        dataset_id = str(table.get("dataset_id"))
        values = [
            v
            for column in (table.get("categories") or {})
            if total_value(dataset_id, column) is None
            for v in codelist_of(table, column)
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
    """Return a column's values when there are few enough to offer as options."""
    values = codelist(str(table["dataset_id"]), column)
    return values if len(values) <= 6 else []


def inherit_from_prior(
    plan: InterpretationPlan,
    intent: QueryIntent,
    prior: InterpretationPlan,
    table: Mapping[str, Any],
) -> InterpretationPlan:
    """A follow-up keeps the slots it neither names nor marks as changed (design Section 5):
    "What was the crime rate that year?" keeps the prior year; "And Maharashtra?" keeps the
    measure and the period. Places and indicators carry over within the same table only.
    Nothing carries over when intent v7 marks the question as a new topic (`follow_up` False).
    """
    if intent.follow_up is False:
        return plan
    changed = set(intent.changed_slots)
    update: dict[str, Any] = {}
    same_table = prior.dataset_id == plan.dataset_id
    types = set(table.get("period_types", []))
    keep_period = not intent.period_mentions and "period" not in changed and prior.periods
    if keep_period and (same_table or all(p.type in types for p in prior.periods)):
        update["periods"] = prior.periods
        update["assumptions"] = [a for a in plan.assumptions if a.code != "D1"]
    keep_place = not intent.place_mentions and not intent.all_places_level
    if same_table and keep_place and "place" not in changed and prior.places:
        update["places"] = prior.places
        update["exclude_total_rows"] = prior.exclude_total_rows
    if same_table and not intent.indicator_ids and "indicator" not in changed:
        update["indicators"] = prior.indicators
    return plan.model_copy(update=update) if update else plan


def check_plan_indicators(sql: str, plan: InterpretationPlan) -> None:
    """Every indicator id the query compares against must be one of the plan's. A query that
    names another id (UI test, 19 Nov: an id invented by editing the planned one, which matched
    no row and led to a slow regeneration) is sent to repair before it runs."""
    allowed = {i.indicator_id for i in plan.indicators}
    if not allowed:
        return
    import sqlglot
    from sqlglot import exp

    used: set[str] = set()
    for node in sqlglot.parse_one(sql, read="duckdb").find_all(exp.EQ, exp.In):
        if any(c.name == "indicator_id" for c in node.find_all(exp.Column)):
            used |= {lit.this for lit in node.find_all(exp.Literal) if lit.is_string}
    unknown = sorted(used - allowed)
    if unknown:
        raise ValueError(f"indicator_id {unknown} is not in the plan; use only {sorted(allowed)}")


def check_missing_values_kept(sql: str, plan: InterpretationPlan) -> None:
    """A value the publisher suppressed or did not report is answered as "not published", with
    its flag (rule sheet E14). A query that drops such rows (`value IS NOT NULL`, or a filter on
    `quality_flag` other than excluding 'implausible') turns that answer into an empty result,
    so it is sent to repair. A ranking (or a highest or lowest value) may drop missing values:
    it orders the published ones."""
    if plan.operation == "ranking":
        return
    import sqlglot
    from sqlglot import exp

    tree = sqlglot.parse_one(sql, read="duckdb")
    orders = any(
        isinstance(o.this, exp.Column) and o.this.name == "value"
        for o in tree.find_all(exp.Ordered)
    )
    if orders or any(True for _ in tree.find_all(exp.Window, exp.Max, exp.Min)):
        return  # the query ranks or picks the highest or lowest published value
    for where in tree.find_all(exp.Where):
        for negation in where.find_all(exp.Not):
            inner = negation.this
            if (
                isinstance(inner, exp.Is)
                and isinstance(inner.expression, exp.Null)
                and isinstance(inner.this, exp.Column)
                and inner.this.name == "value"
            ):
                raise ValueError(
                    "do not filter value IS NOT NULL: a missing or suppressed value is "
                    "reported with its quality_flag"
                )
        for test in where.find_all(exp.EQ, exp.NEQ, exp.In):
            if not any(c.name == "quality_flag" for c in test.find_all(exp.Column)):
                continue
            sides = test.expressions if isinstance(test, exp.In) else [test.expression]
            literals = {s.this for s in sides if isinstance(s, exp.Literal) and s.is_string}
            excludes_implausible = isinstance(test, exp.NEQ) and literals == {"implausible"}
            negated_in = isinstance(test.parent, exp.Not) and literals == {"implausible"}
            if not (excludes_implausible or negated_in):
                raise ValueError(
                    "filter quality_flag only with quality_flag <> 'implausible': suppressed "
                    "and missing values are reported, not dropped"
                )


def make_tool_nodes(deps: ToolNodeDependencies) -> dict[str, NodeFn]:
    """Return graph node overrides; callers combine them with the control and model nodes."""

    def plan_for(
        intent: QueryIntent, state: AnalystState, table: Mapping[str, Any]
    ) -> InterpretationPlan:
        """The plan of one intent: resolution, follow-up inheritance and the slot rules."""
        db = deps.database_for(intent.dataset_id)
        try:
            plan = resolve_plan(
                intent,
                dataset=table,
                indicators=indicators_of(dict(table)),
                db=db,
                refs=deps.refs,
                catalogue=deps.catalogue,
            )
        finally:
            db.close()
        if state.prior_plan is not None:
            plan = inherit_from_prior(plan, intent, state.prior_plan, table)
        plan = _period_options(plan, intent, table, deps)
        plan = _missing_measure_category(plan, intent, table)
        plan = _missing_place(plan, intent, table)
        plan = _ambiguous_category(plan, intent, table, deps)
        if intent.action == "clarify" and not plan.unresolved:
            # The intent asks for a detail the question leaves out; coverage turns an
            # unresolved slot into a clarification.
            missing = _missing_slot(intent)
            stated = bool(intent.period_mentions)
            snapshot = table.get("coverage_start") == table.get("coverage_end") is not None
            if missing == "period" and plan.periods and (stated or snapshot):
                # A period rule already applies: the period the user stated resolved (a bare
                # year read as the table's year type), or the table has one period only (a
                # snapshot). Answer with it and state it. A question without a period on a
                # table with many periods keeps the clarification, so a named event without
                # dates is still asked (dev ladder, 19 Nov: with guidance cards the model asked
                # for periods the rules supply, in v1 and v2).
                if not any(a.code in {"D1", "D7"} for a in plan.assumptions):
                    labels = ", ".join(w.label for w in plan.periods)
                    plan = plan.model_copy(
                        update={
                            "assumptions": [
                                *plan.assumptions,
                                Assumption(code="PERIOD_RULE", text=f"Period used: {labels}."),
                            ]
                        }
                    )
            elif _single_measure(
                missing, options := _clarify_options(missing, intent, table, deps), plan
            ):
                # Only one measure fits and the plan already holds it (dev run 3, e2e-047:
                # "Options: Crime rate, total"): answer with it and say so.
                plan = plan.model_copy(
                    update={
                        "assumptions": [
                            *plan.assumptions,
                            Assumption(
                                code="ONLY_OPTION",
                                text=f"{options[0]} is the only measure of this kind in the "
                                "table, so it is used.",
                            ),
                        ]
                    }
                )
            else:
                plan = plan.model_copy(
                    update={
                        "unresolved": [
                            UnresolvedSlot(
                                slot=missing, mention=intent.reason or "", options=options
                            )
                        ]
                    }
                )
        elif intent.action == "clarify" and intent.missing_slot and plan.unresolved:
            first = min(SLOT_ORDER.index(u.slot) for u in plan.unresolved)
            if SLOT_ORDER.index(intent.missing_slot) < first:
                # The commodity is asked before an unmatched market (rule S1).
                asked = UnresolvedSlot(
                    slot=intent.missing_slot,
                    mention=intent.reason or "",
                    options=_clarify_options(intent.missing_slot, intent, table, deps),
                )
                plan = plan.model_copy(update={"unresolved": [asked, *plan.unresolved]})
        return _order_slots(plan)

    def resolve(state: AnalystState) -> dict[str, Any]:
        """Resolve places, periods and units of the intent into a plan."""
        if state.intent is None:
            return {
                "node_error": "backend_error",
                "events": stage_event(
                    state, "resolve_places_periods_units", "failure", detail="no parsed intent"
                ),
            }
        table = deps.catalogue.get(state.intent.dataset_id)
        reviewed = review_intent(
            state.intent, table, state.intent.standalone_question or state.question
        )
        changed_intent = {"intent": reviewed} if reviewed != state.intent else {}
        state = state.model_copy(update=changed_intent) if changed_intent else state
        intent = reviewed
        if table is None or intent.action == "decline":
            # No listed table fits, or the intent declines: coverage reports it as not covered.
            # A clarify intent without a table ("during demonetisation": no dates) keeps its
            # missing slot, which coverage turns into a clarification before any table check.
            plan = _no_fit_plan(intent)
            if intent.action == "clarify":
                slot = UnresolvedSlot(
                    slot=_missing_slot(intent), mention=intent.reason or "", options=[]
                )
                plan = plan.model_copy(update={"unresolved": [slot]})
            return {
                "plan": plan,
                **changed_intent,
                "events": stage_event(
                    state,
                    "resolve_places_periods_units",
                    dataset_id=plan.dataset_id,
                    unresolved=len(plan.unresolved),
                ),
            }
        try:
            plan = plan_for(intent, state, table)
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
        return {
            "plan": plan,
            **changed_intent,
            "events": stage_event(
                state, "resolve_places_periods_units", unresolved=len(plan.unresolved)
            ),
        }

    def validate_sql(state: AnalystState) -> dict[str, Any]:
        """Validate the last SQL attempt against the read-only and plan rules."""
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
                check_plan_indicators(attempt.sql, state.plan)
                check_missing_values_kept(attempt.sql, state.plan)
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
        """Execute the validated SQL on the read-only database."""
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
        """Compute the derivations the plan asks for."""
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
        """Run consistency checks on the result."""
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
        """Check that every narrated number matches the result or a derived value."""
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
