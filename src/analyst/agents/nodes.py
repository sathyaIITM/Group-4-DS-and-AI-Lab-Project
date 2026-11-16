from __future__ import annotations
import json
import sqlite3
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from analyst.agents.memory import ConversationMemory
from analyst.agents.runlog import RunLogger
from analyst.agents.state import RunConfig
from analyst.contracts import (
    ChartSpec, Event, EvidenceBundle, InterpretationPlan, QueryIntent,
    RoutingDecision, ScreenResult,
)
from analyst.data.catalogue import load_catalogue
from analyst.tools.charts import select_chart
from analyst.tools.evidence import build_evidence, EvidenceStore
from analyst.tools.catalogue_views import describe_table, search_listing, explain

def _obj(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return value if isinstance(value, dict) else {}

def _event(name: str, **details: Any) -> list[Event]:
    return [Event(stage=name, details=details)]

def receive_request(state: dict[str, Any]) -> dict[str, Any]:
    """Initialise a run and restore its conversation context."""
    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {
        "run_id": state.get("run_id") or str(uuid.uuid4()),
        "conversation_id": state.get("conversation_id") or str(uuid.uuid4()),
        "started_at": state.get("started_at") or now,
        "config": state.get("config") or RunConfig.from_files("v0"),
        "events": _event("receive_request", received_at=now.isoformat()),
    }
    conversation_id = updates["conversation_id"]
    memory = ConversationMemory()
    saved = memory.get(conversation_id)
    for key in ("pending_clarification", "prior_plan", "prior_sql", "prior_result_ref"):
        if state.get(key) is None and saved.get(key) is not None:
            updates[key] = saved[key]
    pending = updates.get("pending_clarification")
    if pending:
        pending_dict = _obj(pending)
        original = str(pending_dict.get("original_question", state.get("question", "")))
        reply = str(state.get("question", ""))
        if reply and reply != original:
            updates["question"] = f"{original}\nClarification reply: {reply}"
            updates["pending_clarification"] = None
    return updates

def screen_request(state: dict[str, Any]) -> dict[str, Any]:
    """Reject oversized or clearly unsafe/prompt-injection requests."""
    question = str(state.get("question", "")).strip()
    patterns = (
        r"ignore (all )?(previous|prior|system) instructions",
        r"reveal (the )?(system prompt|api key|secret)",
        r"\b(drop|delete|truncate)\s+table\b",
    )
    reason = None
    if not question:
        reason = "empty_request"
    elif len(question) > 8000:
        reason = "input_too_long"
    elif any(re.search(pattern, question, re.IGNORECASE) for pattern in patterns):
        reason = "unsafe_instruction"
    result = ScreenResult(passes=reason is None, reason=reason)
    return {"screen": result, "events": _event("screen_request", passes=result.passes, reason=reason)}

def _catalogue():
    return load_catalogue(Path("configs/catalogue.toml"))

def retrieve_catalogue_candidates(state: dict[str, Any]) -> dict[str, Any]:
    """Rank real catalogue tables lexically; the domain label never filters candidates."""
    catalogue = _catalogue()
    tables = catalogue.real_tables()
    query_tokens = set(re.findall(r"[a-z0-9]+", str(state.get("question", "")).lower()))
    docs = [f"{t.name} {t.topic} {t.line} {t.publisher} {' '.join(t.describe_questions)}" for t in tables]
    scores = [sum(token in set(re.findall(r"[a-z0-9]+", doc.lower())) for token in query_tokens)
              for doc in docs]
    ranked = sorted(zip(tables, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    config = _obj(state.get("config"))
    limits = _obj(config.get("limits"))
    top_k = int(limits.get("catalogue_top_k", 4))
    candidates = [{"dataset_id": table.name, "name": table.name, "domain": str(table.domain),
                   "score": float(score), "topic": table.topic}
                  for table, score in ranked[:top_k]]
    prior_plan = _obj(state.get("prior_plan"))
    prior_dataset = prior_plan.get("dataset_id")
    if prior_dataset and all(c["dataset_id"] != prior_dataset for c in candidates):
        try:
            table = catalogue.get(prior_dataset)
            candidates = [{"dataset_id": table.name, "name": table.name,
                           "domain": str(table.domain), "score": 1.0, "topic": table.topic}] + candidates
            candidates = candidates[:top_k]
        except StopIteration:
            pass
    return {"catalogue_candidates": candidates,
            "events": _event("retrieve_catalogue_candidates", count=len(candidates))}

def retrieve_context_and_examples(state: dict[str, Any]) -> dict[str, Any]:
    """Load retrieved catalogue context, guidance cards and verified examples by version."""
    catalogue = _catalogue()
    ids = {str(c.get("dataset_id")) for c in state.get("catalogue_candidates", [])}
    entries = [t.model_dump() for t in catalogue.real_tables() if t.name in ids]
    config = _obj(state.get("config"))
    version = str(config.get("version", "v0"))
    cards_path = Path("configs/rag/guidance_cards.v0.json")
    cards: list[Any] = []
    if version != "v0" and cards_path.exists():
        cards = json.loads(cards_path.read_text(encoding="utf-8"))
    examples_path = Path("data/sample/rag_verified_examples.v0.jsonl")
    examples: list[dict[str, Any]] = []
    if version in {"v2", "v3", "v4", "v5", "v6"} and examples_path.exists():
        for line in examples_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                examples.append(json.loads(line))
    return {"retrieved": {"entries": entries, "cards": cards, "examples": examples,
                          "domain_ranked": bool(state.get("routing"))},
            "events": _event("retrieve_context_and_examples", entries=len(entries),
                             cards=len(cards), examples=len(examples))}

def resolve_routing_decision(state: dict[str, Any]) -> dict[str, Any]:
    """Apply the narrow non-data decline and clarification shortcuts from the graph spec."""
    routing = _obj(state.get("routing"))
    label = str(routing.get("label", "run_sql"))
    probability = float(routing.get("probability", 0.0))
    domain = str(routing.get("domain", "unspecified"))
    config = _obj(state.get("config")); limits = _obj(config.get("limits"))
    shortcut = float(limits.get("shortcut_threshold", 0.9))
    min_score = float(limits.get("candidate_min_score", 0.5))
    candidates = state.get("catalogue_candidates", [])
    has_candidate = any(float(c.get("score", 0)) >= min_score for c in candidates)
    if label == "decline_not_covered" and probability >= shortcut and domain == "other" and not has_candidate:
        label = "decline_shortcut"
    elif label == "ask_clarification" and probability < shortcut:
        label = "run_sql"
    elif label == "explain_result" and not state.get("prior_result_ref"):
        label = "search_catalog"
    elif probability < float(limits.get("routing_floor", 0.5)):
        label = "run_sql"
    decision = RoutingDecision(label=label, domain=domain, probability=probability,
                               backend=str(routing.get("backend", "unknown")),
                               escalated=bool(routing.get("escalated", False)))
    return {"routing": decision, "events": _event("resolve_routing_decision", label=label)}

def describe_from_metadata(state: dict[str, Any]) -> dict[str, Any]:
    catalogue = _catalogue()
    candidates = state.get("catalogue_candidates", [])
    requested = next((c.get("dataset_id") for c in candidates), None)
    if requested is None:
        return {"response_text": "I could not identify a catalogue table to describe.",
                "outcome": "searched", "events": _event("describe_from_metadata", found=False)}
    details = describe_table(catalogue, str(requested))
    text = (f"{details['name']} covers {', '.join(details['periods']) or 'periods not specified'} "
            f"and places {', '.join(details['places']) or 'not specified'}. "
            f"Publisher: {details['publisher'] or 'not specified'}.")
    return {"response_text": text, "outcome": "described",
            "events": _event("describe_from_metadata", dataset_id=requested)}

def search_catalog_entries(state: dict[str, Any]) -> dict[str, Any]:
    results = search_listing(_catalogue(), str(state.get("question", "")), limit=5)
    text = "Catalogue matches: " + "; ".join(
        f"{r['name']} ({r['topic']})" for r in results
    ) if results else "I could not find a matching table in the current catalogue."
    return {"response_text": text, "outcome": "searched",
            "events": _event("search_catalog_entries", count=len(results))}

def explain_from_evidence(state: dict[str, Any]) -> dict[str, Any]:
    evidence_id = state.get("prior_result_ref")
    bundle = EvidenceStore().get(str(evidence_id)) if evidence_id else None
    if bundle is None:
        return {"response_text": "I do not have a stored verified result for this conversation.",
                "outcome": "explained", "events": _event("explain_from_evidence", found=False)}
    text = f"Source: {bundle.source or bundle.dataset_id}. SQL: {bundle.sql or 'not recorded'}."
    return {"response_text": text, "outcome": "explained",
            "events": _event("explain_from_evidence", evidence_id=evidence_id)}

def build_evidence_bundle(state: dict[str, Any]) -> dict[str, Any]:
    result = _obj(state.get("result"))
    attempts = state.get("sql", [])
    latest = _obj(attempts[-1]) if attempts else {}
    plan = _obj(state.get("plan"))
    bundle = build_evidence(dataset_id=str(plan.get("dataset_id") or "unknown"),
        dataset_version=str(result.get("dataset_version") or "unknown"),
        sql=str(latest.get("text") or ""), rows=list(result.get("rows") or []))
    EvidenceStore().put(bundle)
    return {"evidence": bundle, "prior_result_ref": bundle.evidence_id,
            "events": _event("build_evidence_bundle", evidence_id=bundle.evidence_id)}

def select_chart_type(state: dict[str, Any]) -> dict[str, Any]:
    result = _obj(state.get("result"))
    chart = select_chart(list(result.get("rows") or []))
    return {"chart": chart, "events": _event("select_chart_type", chart_type=chart.chart_type)}

def finalize_response(state: dict[str, Any]) -> dict[str, Any]:
    """Persist conversation context and run log once, without altering the outcome."""
    conversation_id = str(state.get("conversation_id", ""))
    pending = _obj(state.get("pending_clarification")) or None
    plan = _obj(state.get("plan")) or None
    attempts = state.get("sql", [])
    latest = _obj(attempts[-1]) if attempts else {}
    memory = ConversationMemory()
    memory.save(conversation_id, pending_clarification=pending, prior_plan=plan,
                prior_sql=latest.get("text"), prior_result_ref=state.get("prior_result_ref"))
    if not state.get("finalized"):
        try:
            RunLogger().write_state(state)
        except sqlite3.Error:
            # Logging must not prevent the already-computed answer from being returned.
            pass
    return {"finalized": True, "events": _event("finalize_response")}
