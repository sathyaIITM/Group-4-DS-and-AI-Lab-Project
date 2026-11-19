"""Run limits: the deadline and the hosted-LLM budget (design document Section 5, edge helper)."""

from __future__ import annotations

from datetime import UTC, datetime

from analyst.agents.state import AnalystState


def elapsed_s(state: AnalystState) -> float:
    """Return seconds elapsed since the run started."""
    started = state.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return (datetime.now(UTC) - started).total_seconds()


def deadline_exceeded(state: AnalystState) -> bool:
    """Return True when the run has passed its deadline."""
    return elapsed_s(state) > state.config.limits.run_deadline_s


def budget_exhausted(state: AnalystState) -> bool:
    """Return True when the run has used its allowed model calls."""
    return state.counters.llm_calls >= state.config.limits.max_llm_calls
