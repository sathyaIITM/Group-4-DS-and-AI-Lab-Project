"""Additions to Section 4 used by the T2 graph nodes (allowed as additions, not renames)."""

from pydantic import Field

from analyst.contracts.common import Contract


class ScreenResult(Contract):
    passes: bool
    reason: str | None = None


class Clarification(Contract):
    """A clarification waiting for the user's reply; kept in conversation memory."""

    original_question: str
    question: str
    options: list[str] = Field(default_factory=list)


class RetryHint(Contract):
    stage: str
    reason: str
    change_required: str
