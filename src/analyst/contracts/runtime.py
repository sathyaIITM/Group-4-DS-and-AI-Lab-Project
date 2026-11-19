"""Additions to Section 4 used by the graph control nodes (allowed as additions, not renames)."""

from pydantic import Field

from analyst.contracts.common import Contract


class ScreenResult(Contract):
    """Whether a request passes input screening, and the reason when it does not."""

    passes: bool
    reason: str | None = None


class Clarification(Contract):
    """A clarification waiting for the user's reply; kept in conversation memory."""

    original_question: str
    question: str
    options: list[str] = Field(default_factory=list)


class RetryHint(Contract):
    """What must change on the next attempt of a stage, and why."""

    stage: str
    reason: str
    change_required: str
