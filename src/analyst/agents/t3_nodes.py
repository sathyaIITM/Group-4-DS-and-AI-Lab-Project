"""Adapters that run T3's node functions inside the graph (design document Sections 5, 7, 8).

`make_t3_nodes` returns the nodes that replace the stubs of `route_tool_and_domain`,
`escalate_to_jev`, `extract_query_intent`, `check_coverage`, `define_supported_scope_and_caveats`,
`generate_sql_with_hosted_llm`, `bounded_sql_repair` and `narrate_from_result_only`, and an
`ask_clarification` that has the question written by the LLM. Pass the result to
`build_graph(overrides=...)`.

Every LLM call goes through the injected `LlmClient`, which increments `counters.llm_calls`
itself; the adapters work on a copy of the counters and return it, so nothing is counted twice.
The `LlmCallRecord` of each call is appended to `llm_records` for the run log. A failure of the
backend sets `node_error`; the next edge then ends the run with `failed / backend_error` (or
`budget_exhausted`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from analyst.agents import nodes as t2
from analyst.agents import templates
from analyst.agents.context import published_catalogue
from analyst.agents.events import stage_event
from analyst.agents.state import AnalystState, Counters
from analyst.contracts import InterpretationPlan, SqlAttempt, SqlDraft
from analyst.decisions import coverage as coverage_rules
from analyst.decisions import router as router_mod
from analyst.decisions.router import Backends, BackendUnavailableError, RouterConfig, RouterContext
from analyst.inference import clarify, intent, narrate, sqlgen
from analyst.inference.llm import BudgetExhaustedError, LlmCallRecord, LlmClient, LlmError

NodeFn = Callable[[AnalystState], dict[str, Any]]
Schemas = Callable[[InterpretationPlan], Mapping[str, Any] | str]


def default_schemas(plan: InterpretationPlan) -> Mapping[str, Any] | str:
    """Column names of the plan's table when its observation file is present."""
    from analyst.agents.context import _obs

    path = _obs(plan.dataset_id)
    if not path.exists():
        return plan.obs_table
    import duckdb

    with duckdb.connect() as con:  # own connection: questions run in parallel threads
        rows = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()
    return {plan.obs_table: {r[0]: r[1] for r in rows}}


@dataclass
class T3Dependencies:
    llm: LlmClient
    router_config: RouterConfig
    backends: Backends
    published: Callable[[], Mapping[str, Mapping[str, Any]]] = published_catalogue
    schemas: Schemas = default_schemas
    jev: Any = None
    errors: list[str] = field(default_factory=list)


def _failed(state: AnalystState, node: str, counters: Counters, error: Exception) -> dict[str, Any]:
    kind = "budget_exhausted" if isinstance(error, BudgetExhaustedError) else "backend_error"
    records = list(getattr(error, "records", []))
    return {
        "node_error": kind,
        "counters": counters,
        "llm_records": records,
        "events": stage_event(
            state, node, "failure", error=type(error).__name__, detail=str(error)
        ),
    }


def _run(
    state: AnalystState, node: str, body: Callable[[Counters], dict[str, Any]]
) -> dict[str, Any]:
    counters = state.counters.model_copy()
    try:
        update = body(counters)
    except (LlmError, BackendUnavailableError, ValueError) as error:
        return _failed(state, node, counters, error)
    update["counters"] = update.get("counters", counters)
    # `bumped` copies would drop llm_calls counted on `counters`; carry it over.
    if update["counters"] is not counters:
        update["counters"] = update["counters"].model_copy(update={"llm_calls": counters.llm_calls})
    update.setdefault("events", stage_event(state, node))
    return update


def _lines(state: AnalystState) -> list[str]:
    """`<dataset_id>: <description>`, the form of the routing training data."""
    return [
        c.get("line") or f"{c['dataset_id']}: {c.get('topic', '')}"
        for c in state.catalogue_candidates
    ]


def make_t3_nodes(deps: T3Dependencies) -> dict[str, NodeFn]:
    llm = deps.llm

    def route(state: AnalystState) -> dict[str, Any]:
        context = RouterContext(has_result=state.prior_result_ref is not None)

        def body(counters: Counters) -> dict[str, Any]:
            result = router_mod.route(
                state.question, context, _lines(state), deps.router_config, deps.backends, counters
            )
            decision = result.decision
            return {
                "routing": decision,
                "router_state": result.state,
                "decision_log": [decision.tool, decision.domain],
                "llm_records": result.llm_calls,
                "events": stage_event(
                    state,
                    "route_tool_and_domain",
                    tool=decision.final_tool,
                    domain=decision.final_domain,
                ),
            }

        return _run(state, "route_tool_and_domain", body)

    def escalate(state: AnalystState) -> dict[str, Any]:
        if state.routing is None or state.router_state is None:
            return {"events": stage_event(state, "escalate_to_jev", escalated=False)}
        updated = router_mod.escalate(
            state.routing, state.router_state, deps.router_config, deps.jev
        )
        changed = [r for r in (updated.tool, updated.domain) if r.escalated]
        return {
            "routing": updated,
            "decision_log": changed,
            "events": stage_event(state, "escalate_to_jev", escalated=bool(changed)),
        }

    def extract(state: AnalystState) -> dict[str, Any]:
        def body(counters: Counters) -> dict[str, Any]:
            result, record = intent.extract_intent(
                state.question, state.retrieved, state.prior_plan, llm, counters, state.history
            )
            return {
                "intent": result,
                "llm_records": [record],
                "events": stage_event(state, "extract_query_intent", action=result.action),
            }

        return _run(state, "extract_query_intent", body)

    def coverage(state: AnalystState) -> dict[str, Any]:
        if state.plan is None:
            return _failed(state, "check_coverage", state.counters, ValueError("no plan to check"))
        domain = state.routing.final_domain if state.routing else None
        result = coverage_rules.check_coverage(state.plan, deps.published(), domain=domain)
        update: dict[str, Any] = {
            "coverage": result,
            "events": stage_event(state, "check_coverage", status=result.status),
        }
        if state.coverage is not None and state.checks is not None:  # re-check after data_absent
            update["counters"] = state.counters.bumped("coverage_rechecks")
        return update

    def restrict(state: AnalystState) -> dict[str, Any]:
        if state.plan is None or state.coverage is None:
            return {}
        result = coverage_rules.restrict(state.plan, state.coverage)
        update: dict[str, Any] = {
            "coverage": result,
            "events": stage_event(
                state, "define_supported_scope_and_caveats", status=result.status
            ),
        }
        if result.supported_plan is not None:
            update["plan"] = result.supported_plan
        return update

    def attempt(state: AnalystState, draft: SqlDraft, kind: str) -> SqlAttempt:
        return SqlAttempt(
            attempt=len(state.sql) + 1,
            kind=kind,
            sql=draft.sql,
            statement=draft.statement,
            valid=True,
            error=None,
            executed_ms=None,
        )

    def hints(state: AnalystState) -> list[str]:
        found = [h.change_required for h in state.retry_hints]
        if state.checks is not None and state.checks.retry_hint:
            found.append(state.checks.retry_hint)
        return found

    def generate(state: AnalystState) -> dict[str, Any]:
        if state.plan is None:
            return _failed(
                state, "generate_sql_with_hosted_llm", state.counters, ValueError("no plan")
            )
        plan = state.plan

        def body(counters: Counters) -> dict[str, Any]:
            regenerate = counters.sql_generations > 0
            draft, record = sqlgen.generate_sql(
                plan,
                deps.schemas(plan),
                state.retrieved,
                state.prior_sql,
                hints(state),
                llm,
                counters,
                regenerate=regenerate,
            )
            kind = "regenerate" if regenerate else "generate"
            return {
                "sql": [attempt(state, draft, kind)],
                "llm_records": [record],
                "counters": counters.bumped("sql_generations"),
                "events": stage_event(state, "generate_sql_with_hosted_llm", kind=kind),
            }

        return _run(state, "generate_sql_with_hosted_llm", body)

    def repair(state: AnalystState) -> dict[str, Any]:
        if state.plan is None or not state.sql:
            return _failed(
                state, "bounded_sql_repair", state.counters, ValueError("nothing to repair")
            )
        plan, last = state.plan, state.sql[-1]

        def body(counters: Counters) -> dict[str, Any]:
            draft = SqlDraft(sql=last.sql, statement=last.statement)
            error = last.error or last.error_class
            fixed, record = sqlgen.repair_sql(
                draft, error, deps.schemas(plan), plan.obs_table, llm, counters
            )
            return {
                "sql": [attempt(state, fixed, "repair")],
                "llm_records": [record],
                "counters": counters.bumped("sql_repairs"),
                "events": stage_event(state, "bounded_sql_repair"),
            }

        return _run(state, "bounded_sql_repair", body)

    def narrate_node(state: AnalystState) -> dict[str, Any]:
        if state.evidence is None:
            return _failed(
                state, "narrate_from_result_only", state.counters, ValueError("no evidence")
            )
        evidence = state.evidence

        def body(counters: Counters) -> dict[str, Any]:
            number = counters.narrations + 1
            standalone = state.intent.standalone_question if state.intent else None
            result, record = narrate.narrate(
                evidence, hints(state), llm, counters, attempt=number, question=standalone
            )
            return {
                "narration": [result],
                "llm_records": [record],
                "counters": counters.bumped("narrations"),
                "events": stage_event(state, "narrate_from_result_only", attempt=number),
            }

        return _run(state, "narrate_from_result_only", body)

    def clarification(state: AnalystState) -> dict[str, Any]:
        """The T2 node, with the question text written by the LLM when it can be."""
        update = t2.ask_clarification(state)
        slot = state.plan.unresolved[0] if state.plan and state.plan.unresolved else None
        options = list(slot.options) if slot else []
        counters = state.counters.model_copy()
        try:
            text, record = clarify.write_clarification(
                state.question, slot.slot if slot else "indicator", options, llm, counters
            )
        except (LlmError, ValueError) as error:  # keep the fixed-text question
            update["counters"] = counters
            update["llm_records"] = list(getattr(error, "records", []))
            return update
        pending = update["pending_clarification"].model_copy(update={"question": text})
        update.update(
            response_text=templates.clarification(text, options),
            pending_clarification=pending,
            llm_records=[record],
            counters=counters.bumped("clarifications"),
        )
        return update

    return {
        "route_tool_and_domain": route,
        "escalate_to_jev": escalate,
        "extract_query_intent": extract,
        "check_coverage": coverage,
        "define_supported_scope_and_caveats": restrict,
        "generate_sql_with_hosted_llm": generate,
        "bounded_sql_repair": repair,
        "narrate_from_result_only": narrate_node,
        "ask_clarification": clarification,
    }


def jev_client(model_config: Path | None = None) -> Any:
    """The hosted Jev client (first backend in `model.yaml` `jev.backends`). Raises when its key
    is not set, so a Jev experiment never runs on the LLM fallback without notice."""
    import os

    import yaml

    from analyst.decisions.system_one import SystemOneClient

    path = model_config or Path("configs/model.yaml")
    jev = yaml.safe_load(path.read_text(encoding="utf-8"))["jev"]
    backend = jev["backends"][0]
    key = os.environ.get(backend["api_key_env"])
    if not key:
        raise RuntimeError(f"{backend['api_key_env']} is not set; Jev routing needs it")
    return SystemOneClient(backend["base_url"], jev["model"], api_key=key, timeout_s=10.0)


def live_t3_nodes(version: str, variant: str | None = None) -> dict[str, NodeFn]:
    """T3 nodes on the real LLM client, built from `configs/model.yaml` and the environment.
    A `variant` from `configs/inference.yaml` (for example `jev_routing`) changes the decision
    backends; Jev is connected whenever a chain names it.

    Calling a node with this client spends the project's cloud credit (and Jev credit).
    """
    client = LlmClient.from_config()
    config = RouterConfig.from_files(version, variant=variant)
    uses_jev = any("jev" in chain for chain in config.chains.values())
    jev = jev_client() if uses_jev else None
    from analyst.agents.context import _obs, published_catalogue
    from analyst.agents.tool_nodes import ToolNodeDependencies, make_tool_nodes
    from analyst.tools.sql_runner import ReadOnlyDatabase

    def database_for(dataset_id: str) -> ReadOnlyDatabase:
        if not dataset_id.isidentifier() or dataset_id.lower() != dataset_id:
            raise ValueError("invalid dataset identifier")
        return ReadOnlyDatabase({f"obs_{dataset_id}": _obs(dataset_id)})

    refs_dir = Path("configs/reference")
    tool_nodes = make_tool_nodes(
        ToolNodeDependencies(
            catalogue=published_catalogue(),
            refs={
                "imd_subdivisions": refs_dir / "imd_subdivisions.csv",
                "place_aliases": refs_dir / "place_aliases.csv",
                "subdivision_aliases": refs_dir / "subdivision_aliases.csv",
            },
            database_for=database_for,
        )
    )
    return {
        **make_t3_nodes(T3Dependencies(client, config, Backends(jev=jev, llm=client), jev=jev)),
        **tool_nodes,
    }


__all__ = ["LlmCallRecord", "T3Dependencies", "live_t3_nodes", "make_t3_nodes"]
