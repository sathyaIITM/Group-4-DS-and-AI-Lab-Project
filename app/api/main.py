"""API and agent service.

Scaffold only. The fixed LangGraph workflow is not implemented yet; the stream
endpoint emits the typed event sequence the user interface expects so that the
Compose stack behind Caddy can be checked end to end (week-1 check).
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from analyst import __version__

app = FastAPI(title="India analyst agent", version=__version__)

# Pause between placeholder events; raised in the week-1 check so that buffering is visible.
EVENT_DELAY_S = float(os.environ.get("STREAM_EVENT_DELAY_S", "0.1"))

EventName = Literal["plan", "tool", "sql", "result", "answer", "confidence", "done"]


class AskRequest(BaseModel):
    """A question put to the agent."""

    question: str = Field(min_length=1, max_length=2000)


class StreamEvent(BaseModel):
    """One streamed event. The user interface renders events in arrival order."""

    name: EventName
    payload: dict[str, object] = Field(default_factory=dict)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by Compose and the edge proxy."""
    return {"status": "ok", "version": __version__}


async def _placeholder_events(question: str) -> AsyncIterator[dict[str, str]]:
    events = [
        StreamEvent(name="plan", payload={"question": question, "steps": []}),
        StreamEvent(
            name="answer",
            payload={
                "text": (
                    "The agent is not implemented yet. This endpoint exists to verify "
                    "that server-sent events reach the browser through Caddy."
                )
            },
        ),
        StreamEvent(name="done", payload={}),
    ]
    for event in events:
        yield {"event": event.name, "data": json.dumps(event.payload)}
        await asyncio.sleep(EVENT_DELAY_S)


@app.post("/stream")
async def stream(request: AskRequest) -> EventSourceResponse:
    """Stream the answer as server-sent events."""
    return EventSourceResponse(_placeholder_events(request.question))
