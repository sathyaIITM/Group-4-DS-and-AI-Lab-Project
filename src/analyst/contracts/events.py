"""Streamed events (design document Section 4.7)."""

from datetime import datetime
from typing import Any, Literal

from analyst.contracts.common import Contract

EventType = Literal[
    "run_started",
    "stage",
    "clarification",
    "decline",
    "abstention",
    "failure",
    "answer",
    "evidence",
    "explanation",
    "chart",
    "done",
]


class Event(Contract):
    """A streamed run event with its type, sequence number, time, stage and payload."""

    type: EventType
    run_id: str
    seq: int
    at: datetime
    stage: str | None
    payload: dict[str, Any]
