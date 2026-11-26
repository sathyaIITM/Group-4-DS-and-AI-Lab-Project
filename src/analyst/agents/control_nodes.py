"""Control nodes of the agent graph: intake, routing, retrieval, evidence and replies.

Design document Section 5.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analyst.agents import templates
from analyst.agents.clarify_reply import read_reply
from analyst.agents.context import catalogue_block, published_catalogue, table_context
from analyst.agents.events import stage_event
from analyst.agents.limits import budget_exhausted, deadline_exceeded
from analyst.agents.memory import ANSWER_CHARS, ConversationMemory
from analyst.agents.runlog import RunLogger
from analyst.agents.state import AnalystState, RunConfig
from analyst.contracts import Cause, Clarification, InterpretationPlan, MissingPart, ScreenResult
from analyst.data.catalogue import Catalogue, load_catalogue
from analyst.inference.clarify import fixed_question, slot_detail
from analyst.tools.catalogue_views import describe_table, search_listing
from analyst.tools.charts import select_chart
from analyst.tools.evidence import (
    EvidenceStore,
    build_evidence,
    is_current,
)
from analyst.tools.evidence import (
    load_catalogue as load_published,
)

INJECTION_PATTERNS = (
    r"ignore (all )?(previous|prior|system) instructions",
    r"reveal (the )?(system prompt|api key|secret)",
    r"\b(drop|delete|truncate)\s+table\b",
)
MAX_QUESTION_CHARS = 8000


def receive_request(state: AnalystState) -> dict[str, Any]:
    """Initialise a run and restore its conversation context."""
    now = datetime.now(UTC)
    updates: dict[str, Any] = {
        "run_id": state.run_id or str(uuid.uuid4()),
        "conversation_id": state.conversation_id or str(uuid.uuid4()),
        "started_at": state.started_at or now,
    }
    saved = ConversationMemory().get(updates["conversation_id"])
    if state.prior_plan is None and saved.get("prior_plan"):
        updates["prior_plan"] = InterpretationPlan.model_validate(saved["prior_plan"])
    for key in ("prior_sql", "prior_result_ref"):
        if getattr(state, key) is None and saved.get(key) is not None:
            updates[key] = saved[key]
    if not state.history and saved.get("history"):
        updates["history"] = saved["history"]
    pending = state.pending_clarification
    if pending is None and saved.get("pending_clarification"):
        pending = Clarification.model_validate(saved["pending_clarification"])
    reading = None
    if pending is not None and state.question and state.question != pending.original_question:
        # Code reads "second one", "yes" or "neither" against the offered options, so the router
        # and the intent model receive one complete question (clarify_reply module).
        reading = read_reply(state.question, pending)
        updates["question"] = reading.question
        updates["pending_clarification"] = None
    updates["events"] = stage_event(
        state,
        "receive_request",
        event_type="run_started",
        **({"clarification_reply": reading.kind, "option": reading.option} if reading else {}),
    )
    return updates


def screen_request(state: AnalystState) -> dict[str, Any]:
    """Reject empty, oversized or clearly unsafe requests; on doubt the request passes."""
    question = state.question.strip()
    reason = None
    if not question:
        reason = "empty_request"
    elif len(question) > MAX_QUESTION_CHARS:
        reason = "input_too_long"
    elif any(re.search(p, question, re.IGNORECASE) for p in INJECTION_PATTERNS):
        reason = "unsafe_instruction"
    result = ScreenResult(passes=reason is None, reason=reason)
    return {
        "screen": result,
        "events": stage_event(state, "screen_request", passes=result.passes, reason=reason),
    }


def _catalogue() -> Catalogue:
    """Load the table catalogue configuration."""
    return load_catalogue(Path("configs/catalogue.toml"))


def _lexical_ranking(question: str) -> list[tuple[str, float]]:
    """Word-overlap ranking over the router catalogue; the fallback when no embedder loads."""
    tables = _catalogue().real_tables()
    query_tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    docs = [
        f"{t.name} {t.topic} {t.line} {t.publisher} {' '.join(t.describe_questions)}"
        for t in tables
    ]
    scores = [
        float(sum(token in set(re.findall(r"[a-z0-9]+", doc.lower())) for token in query_tokens))
        for doc in docs
    ]
    ranked = sorted(zip(tables, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [(t.name, score) for t, score in ranked]


def rank_catalogue(question: str, k: int) -> tuple[list[tuple[str, float]], str]:
    """Hybrid ranking (`retrieval.catalogue`), or lexical when the index cannot be built."""
    try:
        from analyst.retrieval.catalogue import rank_tables

        return rank_tables(question, k), "hybrid"
    except Exception as error:  # missing release files or embedding model
        return _lexical_ranking(question), f"lexical ({type(error).__name__})"


def retrieve_catalogue_candidates(state: AnalystState) -> dict[str, Any]:
    """Rank catalogue tables (hybrid, see `retrieval.catalogue`); the domain never filters."""
    catalogue = _catalogue()
    known = {t.name: t for t in catalogue.real_tables()}
    top_k = state.config.limits.catalogue_top_k
    ranking, method = rank_catalogue(state.question, top_k)
    candidates = [
        {
            "dataset_id": name,
            "name": name,
            "domain": str(known[name].domain),
            "score": score,
            "topic": known[name].topic,
            "line": known[name].line,
        }
        for name, score in ranking
        if name in known
    ][:top_k]
    # The previous turn's table is not put among the router's candidates: the router sees the
    # top-k of this question only, built as in training (decision of 2026-11-05). The intent
    # context adds it (retrieve_context_and_examples), so a follow-up can stay on that table.
    return {
        "catalogue_candidates": candidates,
        "events": stage_event(
            state, "retrieve_catalogue_candidates", count=len(candidates), method=method
        ),
    }


def _existing(*paths: str) -> Path | None:
    """Return the first of the given paths that exists, or None."""
    return next((Path(p) for p in paths if Path(p).exists()), None)


def retrieve_context_and_examples(state: AnalystState) -> dict[str, Any]:
    """Catalogue context, guidance cards and verified examples, by version.

    v0 gets the candidate tables with their indicators; v1 adds the guidance cards (as text); v2
    and later add verified examples. Cards and examples are those of the candidate tables, plus
    the analysis SOP cards that belong to no table. The v1 files are used when present,
    otherwise the v0 files. The result has the shape that `inference.intent.context_payload`
    reads (`tables`, `indicators`, `categories`, `cards`).
    """
    ids = [str(c.get("dataset_id")) for c in state.catalogue_candidates]
    prior = state.prior_plan.dataset_id if state.prior_plan else None
    if prior and prior != "none_fit" and prior not in ids:
        ids.append(prior)  # a follow-up may stay on the previous turn's table
    pointer = state.intent.catalogue_dataset_id if state.intent else None
    if state.retrieved and pointer:
        # Widened search after not_covered, intent v7: exactly the table the intent named.
        ids = [*ids, pointer] if pointer not in ids else ids
    elif state.retrieved:
        # Widened search after not_covered: the next tables of the ranking join the candidates.
        top_k = state.config.limits.catalogue_top_k
        ranking, _ = rank_catalogue(state.question, top_k)
        known = {t.name for t in _catalogue().real_tables()}
        more = [name for name, _ in ranking if name in known and name not in ids]
        ids = [*ids, *more[:top_k]]
    version, rag = state.config.version, state.config.rag
    retrieved: dict[str, Any] = table_context(published_catalogue(), ids, state.question)
    cards: list[dict[str, Any]] = []
    examples: list[dict[str, Any]] = []
    if version != "v0":
        path = _existing(rag.cards, rag.cards_fallback)
        if path:
            every = json.loads(path.read_text(encoding="utf-8"))["cards"]
            cards = [c for c in every if c.get("dataset_id") in {*ids, None}]
    if version not in {"v0", "v1"}:
        path = _existing(rag.examples, rag.examples_fallback)
        if path:
            lines = path.read_text(encoding="utf-8").splitlines()
            every = [json.loads(line) for line in lines if line.strip()]
            examples = [e for e in every if e.get("dataset_id") in ids]
    retrieved.update(
        catalogue_block=catalogue_block(),
        cards=[c["body"] for c in cards],
        card_ids=[c["id"] for c in cards],
        examples=[{"question": e.get("question"), "sql": e.get("sql")} for e in examples],
        example_ids=[e["id"] for e in examples],
        domain_ranked=state.routing is not None,
    )
    # A second entry follows a not_covered result: it is the widened search.
    counters = state.counters.bumped("widened_searches") if state.retrieved else state.counters
    return {
        "retrieved": retrieved,
        "counters": counters,
        "events": stage_event(
            state,
            "retrieve_context_and_examples",
            tables=len(retrieved["tables"]),
            cards=len(cards),
            examples=len(examples),
        ),
    }


# A question about a table (rule sheet E3): its coverage, units, columns, definitions or method.
_DESCRIBE = re.compile(
    r"\b(?:cover|covers|covered|coverage|units?|columns?|defin\w*|stand for|stands for|"
    r"methods?|methodology|spelt|spelled|spelling)\b|\bwhat does \S+ mean\b|\bmeans? in\b"
)
# A question about which data exists (rule E2) stays a search.
_SEARCH = re.compile(
    r"\b(?:is there|are there|any data|which data|what data|which datasets?|which sources?|"
    r"what sources?|where can|do you have|available)\b"
)


def asks_about_a_table(question: str) -> bool:
    """True for "What does the PLFS table cover?" or "In what unit are mandi prices
    reported?"; false for "Is there data on rainfall?" (a search, rule E2)."""
    text = question.casefold()
    return bool(_DESCRIBE.search(text)) and not _SEARCH.search(text)


def resolve_routing_decision(state: AnalystState) -> dict[str, Any]:
    """The two shortcuts of the graph specification; every other label keeps its branch.

    A threshold that is None switches its rule off. Decline shortcut: a confident
    `decline_not_covered` for a non-data message (domain `other`) with no candidate table at or
    above `candidate_min_score`. Early clarification: a confident `ask_clarification`; otherwise
    it takes the full retrieval path. `explain_result` without a stored result becomes a search.
    """
    if state.routing is None:
        msg = "resolve_routing_decision needs a routing decision"
        raise ValueError(msg)
    routing, limits = state.routing, state.config.limits
    tool = routing.final_tool
    probability = max(routing.tool.probabilities.values(), default=0.0)
    shortcut, min_score = limits.shortcut_threshold, limits.candidate_min_score
    branch = routing.branch
    if tool == "decline_not_covered":
        has_candidate = min_score is not None and any(
            float(c.get("score", 0)) >= min_score for c in state.catalogue_candidates
        )
        decline = (
            shortcut is not None
            and min_score is not None
            and probability >= shortcut
            and routing.final_domain == "other"
            and not has_candidate
        )
        branch = "decline" if decline else "query"
    elif tool == "ask_clarification":
        early = shortcut is not None and probability >= shortcut
        branch = "clarify" if early else "query"
    elif tool == "explain_result" and not state.prior_result_ref:
        tool, branch = "search_catalog", "search"
    elif tool == "search_catalog" and asks_about_a_table(state.question):
        # Rule sheet E3 before E2: a question about a table's coverage, units or definitions
        # is described from the catalogue, not answered with a list of tables (T2 fix C4).
        tool, branch = "describe_table", "describe"
    decision = routing.model_copy(update={"final_tool": tool, "branch": branch})
    return {
        "routing": decision,
        "events": stage_event(state, "resolve_routing_decision", tool=tool, branch=branch),
    }


def describe_from_metadata(state: AnalystState) -> dict[str, Any]:
    """Describe a table from its catalogue metadata without querying data."""
    catalogue = _catalogue()
    requested = next((c.get("dataset_id") for c in state.catalogue_candidates), None)
    if requested is None:
        return {
            "response_text": "No catalogue table matches the request.",
            "outcome": "searched",
            "events": stage_event(state, "describe_from_metadata", found=False),
        }
    details = describe_table(catalogue, str(requested))
    labels = list(details["periods"])
    periods = (
        f"{labels[0]} to {labels[-1]}" if len(labels) > 3 else ", ".join(labels)
    ) or "periods not specified"
    places = ", ".join(details["places"]) or "not specified"
    publisher = details["publisher"] or "not specified"
    text = f"{details['name']} covers {periods} and places {places}. Publisher: {publisher}."
    return {
        "response_text": text,
        "outcome": "described",
        "events": stage_event(state, "describe_from_metadata", dataset_id=requested),
    }


def search_catalog_entries(state: AnalystState) -> dict[str, Any]:
    """List the catalogue tables that best match the question."""
    results = search_listing(_catalogue(), state.question, limit=5)
    if results:
        text = "Catalogue matches: " + "; ".join(f"{r['name']} ({r['topic']})" for r in results)
    else:
        text = "No table in the current catalogue matches the request."
    return {
        "response_text": text,
        "outcome": "searched",
        "events": stage_event(state, "search_catalog_entries", count=len(results)),
    }


def explain_from_evidence(state: AnalystState) -> dict[str, Any]:
    """Explain the previous answer from its stored evidence bundle."""
    ref = state.prior_result_ref
    bundle = EvidenceStore().get(ref) if ref else None
    if bundle is None:
        return {
            "response_text": "No stored result exists for this conversation.",
            "outcome": "explained",
            "events": stage_event(state, "explain_from_evidence", found=False),
        }
    sources = "; ".join(f"{s.title} ({s.publisher}, {s.dataset_version})" for s in bundle.sources)
    text = f"Source: {sources}. Query: {bundle.sql}. Statement: {bundle.statement}."
    return {
        "response_text": text,
        "outcome": "explained",
        "events": stage_event(state, "explain_from_evidence", evidence_id=ref),
    }


def build_evidence_bundle(state: AnalystState) -> dict[str, Any]:
    """Build the evidence bundle for the current result and store it."""
    bundle = build_evidence(state)
    EvidenceStore().put(bundle)
    return {
        "evidence": bundle,
        "prior_result_ref": bundle.evidence_id,
        "events": stage_event(state, "build_evidence_bundle", evidence_id=bundle.evidence_id),
    }


def select_chart_type(state: AnalystState) -> dict[str, Any]:
    """Choose a chart type for the result by rules."""
    chart = select_chart(state.plan, state.result)
    return {
        "chart": chart,
        "events": stage_event(state, "select_chart_type", chart_type=chart.chart_type),
    }


def history_turn(state: AnalystState) -> dict[str, Any]:
    """What intent v7 sees of a finished turn: the question, how it was read, and the answer
    (cut to ANSWER_CHARS). Plan slots are names and labels, not codes."""
    plan = state.plan if state.plan and state.plan.dataset_id != "none_fit" else None
    intent = state.intent
    pending = state.pending_clarification
    turn: dict[str, Any] = {
        "question": state.question,
        "standalone_question": intent.standalone_question if intent else None,
        "outcome": state.outcome,
        "dataset_id": plan.dataset_id if plan else None,
        "indicators": [i.label for i in plan.indicators] if plan else [],
        "places": [p.name for p in plan.places] if plan else [],
        "all_places_level": plan.all_places_level if plan else None,
        "periods": [w.label for w in plan.periods] if plan else [],
        "categories": plan.categories if plan else {},
        "answer": (state.response_text or "")[:ANSWER_CHARS],
    }
    if pending is not None:
        turn["clarification"] = {"question": pending.question, "options": pending.options}
    return turn


def finalize_response(state: AnalystState) -> dict[str, Any]:
    """Persist conversation context and the run log once, without altering the outcome."""
    pending = state.pending_clarification
    latest = state.sql[-1] if state.sql else None
    ConversationMemory().save(
        state.conversation_id,
        pending_clarification=pending.model_dump(mode="json") if pending else None,
        prior_plan=state.plan.model_dump(mode="json") if state.plan else None,
        prior_sql=latest.sql if latest else None,
        prior_result_ref=state.prior_result_ref,
        turn=history_turn(state),
    )
    done = stage_event(state, "finalize_response", "done")
    if not state.finalized:
        # The log includes the `done` event; logging must not prevent the answer being returned.
        final = state.model_copy(update={"events": [*state.events, *done], "finalized": True})
        with contextlib.suppress(sqlite3.Error):
            RunLogger().write_state(final)
    return {"finalized": True, "events": done}


def failure_cause(state: AnalystState) -> Cause:
    """Why the run failed: a backend failure, the latest detected fault, then the LLM budget."""
    if state.node_error:
        return state.node_error
    if state.validation_result != "valid":
        return "sql_invalid"
    if state.execution_result != "success":
        return "execution_error"
    if state.checks is not None and state.checks.verdict == "query_fault":
        return "result_check_failed"
    if budget_exhausted(state):
        return "budget_exhausted"
    return "backend_error"


def abstention_cause(state: AnalystState) -> Cause:
    """Why the run abstained, in order of precedence."""
    if deadline_exceeded(state):
        return "deadline_exceeded"
    if state.checks is not None and state.checks.verdict in {"empty_result", "data_absent"}:
        return "no_rows"
    if state.number_check is not None and not state.number_check.passed:
        return "unverified"
    if state.verification is not None and state.verification.claims_supported is False:
        return "unverified"
    if state.answer_decision != "answer":
        return "low_confidence"
    return "unverified"


def respond_out_of_scope(state: AnalystState) -> dict[str, Any]:
    """Reply to a request that failed input screening."""
    reason = state.screen.reason if state.screen else None
    return {
        "response_text": templates.out_of_scope(reason),
        "outcome": "out_of_scope",
        "events": stage_event(state, "respond_out_of_scope", reason=reason),
    }


def clarification_detail(state: AnalystState) -> str:
    """The plain word for the first unresolved slot of the plan ("commodity", "market")."""
    if state.plan is None or not state.plan.unresolved:
        return "detail"
    slot = state.plan.unresolved[0]
    table = published_catalogue().get(state.plan.dataset_id)
    return slot_detail(slot.slot, slot.mention, table)


def ask_clarification(state: AnalystState) -> dict[str, Any]:
    """One clarification question; options come from the plan's unresolved slots (code)."""
    slot = state.plan.unresolved[0] if state.plan and state.plan.unresolved else None
    options = list(slot.options) if slot else []
    question = (
        fixed_question(clarification_detail(state), slot.slot, slot.mention) if slot else None
    )
    pending = Clarification(
        original_question=state.question,
        question=question or "",
        options=options,
    )
    return {
        "response_text": templates.clarification(question, options),
        "outcome": "clarifying",
        "pending_clarification": pending,
        "counters": state.counters.bumped("clarifications"),
        "events": stage_event(state, "ask_clarification", "clarification", slot=slot and slot.slot),
    }


DECLINE_KINDS = {"indicator", "period", "place", "geo_level"}


def decline_and_log_data_request(state: AnalystState) -> dict[str, Any]:
    """Decline a question the catalogue cannot answer and record it as a data request."""
    missing = state.coverage.missing if state.coverage else []
    intent = state.intent
    if (
        intent is not None
        and intent.action == "decline"
        and intent.reason
        and all(m.detail.startswith("no table") for m in missing)
    ):
        # The intent's reason says what is missing ("the CPI table ends in December 2023");
        # the generic "no table 'none_fit'" does not (dev run 3, e2e-085).
        kind = intent.missing_slot if intent.missing_slot in DECLINE_KINDS else "indicator"
        missing = [MissingPart(kind=kind, detail=intent.reason.rstrip("."))]
    pointers = state.coverage.pointers if state.coverage else []
    return {
        "response_text": templates.decline(missing, pointers),
        "outcome": "declined",
        "outcome_cause": "not_covered",
        "events": stage_event(
            state, "decline_and_log_data_request", "decline", missing=len(missing)
        ),
    }


def abstain_with_reason(state: AnalystState) -> dict[str, Any]:
    """End the run without an answer and state why."""
    cause = abstention_cause(state)
    return {
        "response_text": templates.abstain(cause),
        "outcome": "abstained",
        "outcome_cause": cause,
        "events": stage_event(state, "abstain_with_reason", "abstention", cause=cause),
    }


def report_system_failure(state: AnalystState) -> dict[str, Any]:
    """End the run with a system-failure message for its cause."""
    cause = failure_cause(state)
    return {
        "response_text": templates.failure(cause),
        "outcome": "failed",
        "outcome_cause": cause,
        "events": stage_event(state, "report_system_failure", "failure", cause=cause),
    }


def validate_existing_result_for_chart(state: AnalystState) -> dict[str, Any]:
    """Chart request: the stored result must exist, be current and hold something to plot
    (more than one value). Otherwise the request is answered as a query for the values to plot,
    with the conversation history (UI test, 19 Nov: "plot the same metric across the age
    categories" after a single value asked an unrelated clarification, then printed "one
    value")."""
    bundle = EvidenceStore().get(state.prior_result_ref) if state.prior_result_ref else None
    live = {k: str(v.get("dataset_version")) for k, v in load_published().items()}
    ok = bundle is not None and (not live or is_current(bundle, live))
    plottable = ok and bundle is not None and select_chart(bundle.plan, bundle.result).vega_lite
    update: dict[str, Any] = {"chart_result": "verified" if plottable else "needs_query"}
    if plottable and bundle is not None:
        update.update(result=bundle.result, plan=bundle.plan, evidence=bundle)
    update["events"] = stage_event(
        state, "validate_existing_result_for_chart", verified=ok, plottable=bool(plottable)
    )
    return update


def assemble_answer_and_evidence_panel(state: AnalystState) -> dict[str, Any]:
    """Assemble the final answer text, badge, chart and evidence reference."""
    text = state.narration[-1].text if state.narration else ""
    badge = state.confidence.badge if state.confidence else "not_verified"
    return {
        "response_text": text,
        "outcome": "answered",
        "events": stage_event(state, "assemble_answer_and_evidence_panel", "answer", badge=badge),
    }


def render_chart(state: AnalystState) -> dict[str, Any]:
    """The Vega-Lite specification is built with the chart type; a chart-only request ends here."""
    chart_type = state.chart.chart_type if state.chart else None
    update: dict[str, Any] = {
        "events": stage_event(state, "render_chart", "chart", chart_type=chart_type)
    }
    if state.outcome is None:
        update["outcome"] = "charted"
        kind = CHART_WORDS.get(str(chart_type), "A chart")
        about = state.evidence.statement if state.evidence else "the previous result"
        update["response_text"] = f"{kind} of the previous result: {about}."
    return update


CHART_WORDS = {
    "line": "A line chart",
    "bar": "A bar chart",
    "horizontal_bar_sorted": "A ranked bar chart",
    "grouped_bar": "A grouped bar chart",
}


__all__ = [
    "RunConfig",
    "abstain_with_reason",
    "abstention_cause",
    "ask_clarification",
    "assemble_answer_and_evidence_panel",
    "build_evidence_bundle",
    "decline_and_log_data_request",
    "describe_from_metadata",
    "explain_from_evidence",
    "failure_cause",
    "finalize_response",
    "receive_request",
    "render_chart",
    "report_system_failure",
    "resolve_routing_decision",
    "respond_out_of_scope",
    "retrieve_catalogue_candidates",
    "retrieve_context_and_examples",
    "screen_request",
    "search_catalog_entries",
    "select_chart_type",
    "validate_existing_result_for_chart",
]
