"""API and agent service: one question in, one answer with its evidence out.

Run from the repository root (the agent reads `configs/` and `data/processed/`):

    AGENT_LLM=stub uvicorn app.api.main:app --port 8000     # no model call, no cost
    AGENT_LLM=live GOOGLE_CLOUD_PROJECT=<project> uvicorn app.api.main:app --port 8000

and open http://localhost:8000/. `AGENT_LLM=live` calls the hosted model and spends cloud
credit; the default is `stub`. Behind Caddy, `/api/*` reaches this service with the prefix
removed, so every route is served both at `/<route>` and at `/api/<route>`.

Routes:
- `POST /ask`: run one turn and return the reply (JSON).
- `POST /stream`: the same turn as server-sent events: one `stage` event per graph node, then
  `answer` (the reply) and `done`.
- `GET /conversations/{conversation_id}`: the turn history kept for the conversation.
- `GET /healthz`: liveness, with the agent mode.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from analyst import __version__

AGENT_LLM = os.environ.get("AGENT_LLM", "stub")  # "live" spends cloud credit
AGENT_VERSION = os.environ.get("AGENT_VERSION", "v0")
AGENT_VARIANT = os.environ.get("AGENT_VARIANT") or None  # e.g. jev_routing (needs Jev's key)
MAX_ROWS = 50  # result rows returned to the browser
UI_PAGE = Path(__file__).resolve().parents[1] / "ui" / "static" / "index.html"

NodeFn = Callable[[Any], dict[str, Any]]

app = FastAPI(title="India analyst agent", version=__version__)
api = APIRouter()

_nodes: dict[str, NodeFn] | None = None
_nodes_lock = threading.Lock()


class AskRequest(BaseModel):
    """One turn of a conversation. Omit `conversation_id` to start a new conversation."""

    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)


def agent_nodes() -> dict[str, NodeFn] | None:
    """The live nodes, built once; None runs the graph's stub nodes (no model call)."""
    global _nodes
    if AGENT_LLM != "live":
        return None
    with _nodes_lock:
        if _nodes is None:
            from analyst.agents.model_nodes import live_model_nodes

            _nodes = live_model_nodes(AGENT_VERSION, AGENT_VARIANT)
    return _nodes


def _initial_state(request: AskRequest) -> Any:
    """Build the starting agent state for a request with the configured version and variant."""
    from analyst.agents.state import AnalystState, RunConfig

    return AnalystState(
        run_id=str(uuid.uuid4()),
        conversation_id=request.conversation_id or str(uuid.uuid4()),
        question=request.question,
        config=RunConfig.from_files(AGENT_VERSION, variant=AGENT_VARIANT),
        meta={"eval_set": "ui", "experiment": f"ui_{AGENT_LLM}"},
    )


def reply_payload(state: Any) -> dict[str, Any]:
    """The reply for the browser, from the final state only (no new figures)."""
    from analyst.agents.memory import ConversationMemory

    result, evidence, plan = state.result, state.evidence, state.plan
    pending = state.pending_clarification
    chart = state.chart
    records = state.llm_records
    payload: dict[str, Any] = {
        "run_id": state.run_id,
        "conversation_id": state.conversation_id,
        "question": state.question,
        "interpreted_as": state.intent.standalone_question if state.intent else None,
        "follow_up": state.intent.follow_up if state.intent else None,
        "outcome": state.outcome,
        "cause": state.outcome_cause,
        "text": state.response_text,
        "options": list(pending.options) if pending else [],
        "badge": state.confidence.badge if state.confidence else None,
        "domain": state.routing.final_domain if state.routing else None,
        "tool": state.routing.final_tool if state.routing else None,
        "chart": (
            {"type": chart.chart_type, "reason": chart.reason, "vega_lite": chart.vega_lite}
            if chart is not None
            else None
        ),
        "evidence": None,
        "llm_calls": len(records),
        "cost_usd_est": round(sum(r.cost_usd_est or 0.0 for r in records), 5),
        "trace": [e.stage for e in state.events if e.stage],
        "history": ConversationMemory().get(state.conversation_id).get("history", []),
    }
    if result is not None and state.outcome in {"answered", "charted"}:
        payload["evidence"] = {
            "dataset_id": plan.dataset_id if plan else None,
            "sources": [s.model_dump(mode="json") for s in evidence.sources] if evidence else [],
            "sql": result.sql,
            "columns": [c.name for c in result.columns],
            "rows": result.rows[:MAX_ROWS],
            "row_count": result.row_count,
            "assumptions": [a.text for a in plan.assumptions] if plan else [],
            "caveats": [c.text for c in evidence.caveats] if evidence else [],
            "checks": [{"name": o.name, "passed": o.passed} for o in (state.checks.outcomes or [])]
            if state.checks
            else [],
            "evidence_id": evidence.evidence_id if evidence else None,
        }
    return payload


def _run(request: AskRequest) -> dict[str, Any]:
    """Run the agent graph to completion for one request and return the reply payload."""
    from analyst.agents.graph import invoke_graph

    return reply_payload(invoke_graph(_initial_state(request), overrides=agent_nodes()))


@api.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by Compose and the edge proxy."""
    return {
        "status": "ok",
        "version": __version__,
        "llm": AGENT_LLM,
        "agent": AGENT_VERSION,
        "variant": AGENT_VARIANT or "",
    }


@api.post("/ask")
async def ask(request: AskRequest) -> dict[str, Any]:
    """Run one turn and return the reply with its evidence."""
    return await asyncio.to_thread(_run, request)


async def _events(request: AskRequest) -> AsyncIterator[dict[str, str]]:
    """Stream graph updates for one request as server-sent events."""
    from analyst.agents.graph import RECURSION_LIMIT, build_graph
    from analyst.agents.state import AnalystState

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    state = _initial_state(request)

    def work() -> None:
        """Run the graph in a worker thread and pass each update to the event queue."""
        final: dict[str, Any] | None = None
        try:
            graph = build_graph(agent_nodes())
            chunks: Any = graph.stream(
                state.model_dump(),
                config={"recursion_limit": RECURSION_LIMIT},
                stream_mode=["updates", "values"],
            )
            for mode, chunk in chunks:
                if mode == "values":
                    final = dict(chunk)
                    continue
                for node, update in dict(chunk or {}).items():
                    events = (update or {}).get("events") or []
                    payload = events[-1].payload if events else {}
                    loop.call_soon_threadsafe(
                        queue.put_nowait, ("stage", {"node": node, "detail": payload})
                    )
            reply = reply_payload(AnalystState.model_validate(final)) if final else None
            loop.call_soon_threadsafe(queue.put_nowait, ("answer", reply))
        except Exception as error:  # the browser gets the failure, not a hung stream
            detail = {"error": type(error).__name__, "detail": str(error)[:300]}
            loop.call_soon_threadsafe(queue.put_nowait, ("error", detail))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", {}))

    threading.Thread(target=work, daemon=True).start()
    while True:
        name, data = await queue.get()
        yield {"event": name, "data": json.dumps(data, default=str)}
        if name == "done":
            break


@api.post("/stream")
async def stream(request: AskRequest) -> EventSourceResponse:
    """The same turn as server-sent events (`stage`, `answer` or `error`, then `done`)."""
    return EventSourceResponse(_events(request))


@api.get("/conversations/{conversation_id}")
async def conversation(conversation_id: str) -> dict[str, Any]:
    """The turns kept for a conversation (at most five, oldest first)."""
    from analyst.agents.memory import ConversationMemory

    if len(conversation_id) > 64:
        raise HTTPException(status_code=400, detail="conversation id too long")
    return {
        "conversation_id": conversation_id,
        "history": ConversationMemory().get(conversation_id).get("history", []),
    }


app.include_router(api)
app.include_router(api, prefix="/api")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """The demo page (behind Caddy the UI container serves the same file)."""
    return FileResponse(UI_PAGE)
