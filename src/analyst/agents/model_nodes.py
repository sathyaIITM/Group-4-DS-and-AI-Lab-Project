"""Graph adapters for the model-backed nodes (design document Sections 5, 7, 8).

`make_model_nodes` returns the nodes that replace the stubs of `route_tool_and_domain`,
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

from analyst.agents import control_nodes, templates
from analyst.agents.context import indicators_of, published_catalogue
from analyst.agents.events import stage_event
from analyst.agents.state import AnalystState, Counters
from analyst.contracts import InterpretationPlan, SqlAttempt, SqlDraft
from analyst.decisions import coverage as coverage_rules
from analyst.decisions import router as router_mod
from analyst.decisions.router import Backends, BackendUnavailableError, RouterConfig, RouterContext
from analyst.inference import clarify, intent, narrate, replies, sqlgen
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
class ModelNodeDependencies:
    """Clients and configuration the model-backed nodes need."""

    llm: LlmClient
    router_config: RouterConfig
    backends: Backends
    published: Callable[[], Mapping[str, Mapping[str, Any]]] = published_catalogue
    schemas: Schemas = default_schemas
    jev: Any = None
    errors: list[str] = field(default_factory=list)


def _failed(state: AnalystState, node: str, counters: Counters, error: Exception) -> dict[str, Any]:
    """Return the state update for a node whose model call failed."""
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
    """Run a node body on a copy of the counters and turn errors into a failure update."""
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


DESCRIBE_FIELDS = (
    "dataset_id",
    "title",
    "source_table",
    "publisher",
    "source_name",
    "period_conventions",
    "geo_levels",
    "coverage_start",
    "coverage_end",
    "period_types",
    "caveats",
)


def _guidance_cards(state: AnalystState) -> list[dict[str, Any]]:
    """The guidance cards in use (documentation for describe answers, in every version)."""
    import json

    rag = state.config.rag
    for name in (rag.cards, rag.cards_fallback):
        path = Path(name)
        if path.exists():
            return list(json.loads(path.read_text(encoding="utf-8")).get("cards", []))
    return []


def _lines(state: AnalystState) -> list[str]:
    """`<dataset_id>: <description>`, the form of the routing training data."""
    return [
        c.get("line") or f"{c['dataset_id']}: {c.get('topic', '')}"
        for c in state.catalogue_candidates
    ]


def make_model_nodes(deps: ModelNodeDependencies) -> dict[str, NodeFn]:
    """Return the model-backed graph nodes built on the given dependencies."""
    llm = deps.llm

    def route(state: AnalystState) -> dict[str, Any]:
        """Decide tool and domain for the question."""
        context = RouterContext(has_result=state.prior_result_ref is not None)

        def body(counters: Counters) -> dict[str, Any]:
            """Call the router and record its decisions."""
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
        """Re-decide uncertain routing decisions on Jev."""
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
        """Extract the query intent from the question."""

        def body(counters: Counters) -> dict[str, Any]:
            """Call intent extraction with the retrieved context and history."""
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
        """Check whether the catalogue covers the resolved plan."""
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
        """Restrict the plan to the part the catalogue supports."""
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
        """Wrap an SQL draft as the next SQL attempt."""
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
        """Collect the retry hints to pass to the next SQL attempt."""
        found = [h.change_required for h in state.retry_hints]
        if state.checks is not None and state.checks.retry_hint:
            found.append(state.checks.retry_hint)
        return found

    def generate(state: AnalystState) -> dict[str, Any]:
        """Generate SQL for the plan with the hosted model."""
        if state.plan is None:
            return _failed(
                state, "generate_sql_with_hosted_llm", state.counters, ValueError("no plan")
            )
        plan = state.plan

        def body(counters: Counters) -> dict[str, Any]:
            """Call SQL generation, regenerating when an earlier attempt failed."""
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
        """Repair the last SQL attempt using its error."""
        if state.plan is None or not state.sql:
            return _failed(
                state, "bounded_sql_repair", state.counters, ValueError("nothing to repair")
            )
        plan, last = state.plan, state.sql[-1]

        def body(counters: Counters) -> dict[str, Any]:
            """Call SQL repair on the last attempt."""
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
        """Narrate the answer from the result and evidence only."""
        if state.evidence is None:
            return _failed(
                state, "narrate_from_result_only", state.counters, ValueError("no evidence")
            )
        evidence = state.evidence

        def body(counters: Counters) -> dict[str, Any]:
            """Call narration for the next attempt."""
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

    def decline(state: AnalystState) -> dict[str, Any]:
        """A decline where no table fits (the router's shortcut, or an intent with `none_fit`):
        a short written reply that says what is covered instead. A message that is not a data
        request, or personal distress, ends as `out_of_scope` and is not logged as a data
        request; distress gets the fixed helpline line. A decline on a named table (a period
        or place the table lacks) keeps the control-node template with the intent's reason."""
        if state.intent is not None and state.intent.dataset_id != "none_fit":
            return control_nodes.decline_and_log_data_request(state)
        counters = state.counters.model_copy()
        # Every catalogue table, not only the retrieved candidates: for "What is the weather
        # today?" the top four held no rainfall table, and the reply named CPI (UI test, 18 Nov).
        lines = [t.line for t in control_nodes._catalogue().real_tables()]
        asked = (state.intent.standalone_question if state.intent else None) or state.question
        try:
            reply, record = replies.write_decline(asked, lines, llm, counters)
        except (LlmError, ValueError) as error:  # keep the fixed decline text
            update = control_nodes.decline_and_log_data_request(state)
            update.update(counters=counters, llm_records=list(getattr(error, "records", [])))
            return update
        if reply.kind == "not_covered":
            update = control_nodes.decline_and_log_data_request(state)
            update.update(response_text=reply.reply.strip())
        else:
            text = reply.reply.strip()
            if reply.kind == "personal_distress":
                text = f"{text} {replies.DISTRESS_HELP}"
            update = {
                "response_text": text,
                "outcome": "out_of_scope",
                "outcome_cause": None,
                "events": stage_event(
                    state, "decline_and_log_data_request", "decline", kind=reply.kind
                ),
            }
        update.update(counters=counters, llm_records=[record])
        return update

    def describe(state: AnalystState) -> dict[str, Any]:
        """`describe_table`: an answer from the catalogue entries and guidance cards only
        ("What is JJAS?"). The previous turn's table comes first, and the recent history is
        given, so "the categories" refers to the last answer. A message that asks for figures
        continues on the query path. When the call fails, the template summary of the same
        tables."""
        prior = state.prior_plan.dataset_id if state.prior_plan else None
        ids = [str(c.get("dataset_id")) for c in state.catalogue_candidates]
        if prior and prior != "none_fit":
            ids = [prior, *[i for i in ids if i != prior]]
        published = deps.published()
        tables = [
            {
                **{k: published[i].get(k) for k in DESCRIBE_FIELDS if k in published[i]},
                "indicators": [
                    f"{x['label']} ({x['unit']})" for x in indicators_of(dict(published[i]))
                ],
            }
            for i in ids
            if i in published
        ]
        cards = [c for c in _guidance_cards(state) if c.get("dataset_id") in {*ids, None}]
        counters = state.counters.model_copy()
        ordered = state.model_copy(
            update={"catalogue_candidates": [{"dataset_id": i} for i in ids]}
        )
        try:
            reply, record = replies.write_description(
                state.question, tables, cards, llm, counters, state.history[-2:]
            )
        except (LlmError, ValueError) as error:
            update = control_nodes.describe_from_metadata(ordered)
            update.update(counters=counters, llm_records=list(getattr(error, "records", [])))
            return update
        if reply.data_request and state.routing is not None:
            routing = state.routing.model_copy(update={"final_tool": "run_sql", "branch": "query"})
            return {
                "routing": routing,
                "counters": counters,
                "llm_records": [record],
                "events": stage_event(state, "describe_from_metadata", handed_to_query=True),
            }
        return {
            "response_text": reply.answer.strip(),
            "outcome": "described",
            "counters": counters,
            "llm_records": [record],
            "events": stage_event(
                state, "describe_from_metadata", documented=reply.documented, tables=len(tables)
            ),
        }

    def explain(state: AnalystState) -> dict[str, Any]:
        """`explain_result`: an answer about the stored result (its source, query, assumptions
        and caveats) written from the evidence only; a message that asks for new figures
        continues on the query path (smoke run, 19 Nov: "How much did it change between those
        two years?" returned the source note)."""
        from analyst.tools.evidence import EvidenceStore

        bundle = EvidenceStore().get(state.prior_result_ref) if state.prior_result_ref else None
        if bundle is None:
            return control_nodes.explain_from_evidence(state)
        documentation = {
            "result": {
                "statement": bundle.statement,
                "sql": bundle.sql,
                "columns": [c.name for c in bundle.result.columns],
                "rows": bundle.result.rows[:20],
            },
            "sources": [s.model_dump(mode="json") for s in bundle.sources],
            "assumptions": [a.text for a in bundle.assumptions],
            "caveats": [c.text for c in bundle.caveats],
        }
        counters = state.counters.model_copy()
        try:
            reply, record = replies.write_description(
                state.question, [documentation], [], llm, counters, state.history[-2:]
            )
        except (LlmError, ValueError) as error:
            update = control_nodes.explain_from_evidence(state)
            update.update(counters=counters, llm_records=list(getattr(error, "records", [])))
            return update
        if reply.data_request and state.routing is not None:
            routing = state.routing.model_copy(update={"final_tool": "run_sql", "branch": "query"})
            return {
                "routing": routing,
                "counters": counters,
                "llm_records": [record],
                "events": stage_event(state, "explain_from_evidence", handed_to_query=True),
            }
        return {
            "response_text": reply.answer.strip(),
            "outcome": "explained",
            "counters": counters,
            "llm_records": [record],
            "events": stage_event(state, "explain_from_evidence", evidence_id=bundle.evidence_id),
        }

    def clarification(state: AnalystState) -> dict[str, Any]:
        """The control node, with the question text written by the LLM when it can be."""
        update = control_nodes.ask_clarification(state)
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
        "decline_and_log_data_request": decline,
        "describe_from_metadata": describe,
        "explain_from_evidence": explain,
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


def live_model_nodes(version: str, variant: str | None = None) -> dict[str, NodeFn]:
    """Model-backed nodes on the real LLM client, from `configs/model.yaml` and the environment.
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
        """Open a read-only database over one dataset's observation table."""
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
        **make_model_nodes(
            ModelNodeDependencies(client, config, Backends(jev=jev, llm=client), jev=jev)
        ),
        **tool_nodes,
    }


__all__ = ["LlmCallRecord", "ModelNodeDependencies", "live_model_nodes", "make_model_nodes"]
