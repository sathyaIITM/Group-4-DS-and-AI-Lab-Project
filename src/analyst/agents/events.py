"""Section 4 events emitted by graph nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from analyst.contracts import Event, EventType

if TYPE_CHECKING:
    from analyst.agents.state import AnalystState


def stage_event(
    state: AnalystState, node: str, event_type: EventType = "stage", **payload: Any
) -> list[Event]:
    """One event for `node`, numbered after the events already in the state."""
    return [
        Event(
            type=event_type,
            run_id=state.run_id,
            seq=len(state.events) + 1,
            at=datetime.now(UTC),
            stage=node,
            payload={k: v for k, v in payload.items() if v is not None},
        )
    ]
