"""Short written replies for the two branches that end without a query.

- `write_decline`: the router chose `decline_not_covered` before any intent was read. The reply
  says what the assistant covers instead, and classifies the message: a data request the
  catalogue does not hold (logged as a data request), a message that is not a data request
  (weather now, code, chat), or personal distress, to which code adds a fixed helpline line.
- `write_description`: the router chose `describe_table` ("What is JJAS?"). The answer uses
  only the catalogue entries and guidance cards given to it, and says so when the term is not
  documented.

Both replies may contain only numbers that appear in their inputs; otherwise the reply is
rejected and the caller falls back to its fixed text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient

DeclineKind = Literal["not_covered", "not_data", "personal_distress"]

# Tele-MANAS, the national tele-mental-health helpline of the Ministry of Health and Family
# Welfare (toll-free, 24 hours). Added by code, never written by the model.
DISTRESS_HELP = (
    "If you are going through a difficult time, you can call Tele-MANAS, the national "
    "mental health helpline, free at any hour on 14416 or 1-800-891-4416."
)
MAX_REPLY_CHARS = 600


class DeclineReply(BaseModel):
    """The kind of decline and the reply text written by the model."""

    model_config = ConfigDict(extra="forbid")

    kind: DeclineKind
    reply: str


class DescribeReply(BaseModel):
    """A description of tables written by the model, or a hand-over to the query path."""

    model_config = ConfigDict(extra="forbid")

    data_request: bool = False  # the message asks for figures: the query path answers it
    documented: bool
    answer: str


def _numbers(text: str) -> set[str]:
    """Return the numbers written in a text."""
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def check_reply(reply: str, sources: str) -> None:
    """Reject an empty or long reply, or one with a number that is not in its inputs."""
    if not reply.strip():
        raise ValueError("empty reply")
    if len(reply) > MAX_REPLY_CHARS:
        raise ValueError("reply too long")
    unknown = _numbers(reply) - _numbers(sources)
    if unknown:
        raise ValueError(f"numbers not in the inputs: {sorted(unknown)[:5]}")


def write_decline(
    question: str,
    catalogue_lines: Sequence[str],
    llm: LlmClient,
    counters: CallCounter,
) -> tuple[DeclineReply, LlmCallRecord]:
    """Write a decline reply with the model."""
    catalogue = list(catalogue_lines)
    sources = question + "\n" + "\n".join(catalogue)
    reply, record = llm.structured(
        "decline",
        "decline",
        {"question": question, "catalogue": catalogue},
        DeclineReply,
        counters=counters,
        validate=lambda r: check_reply(r.reply, sources),
        node="decline_and_log_data_request",
    )
    return reply, record


def write_description(
    question: str,
    tables: Sequence[Mapping[str, Any]],
    cards: Sequence[Mapping[str, Any]],
    llm: LlmClient,
    counters: CallCounter,
    history: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[DescribeReply, LlmCallRecord]:
    """Describe tables from their documentation with the model."""
    documentation = {
        "tables": list(tables),
        "guidance": [{"title": c.get("title"), "text": c.get("body")} for c in cards],
    }
    sources = question + "\n" + json.dumps(documentation, ensure_ascii=False, default=str)

    def validate(reply: DescribeReply) -> None:
        """Check that the description adds no numbers absent from its sources."""
        if not reply.data_request:  # a hand-over to the query path carries no answer text
            check_reply(reply.answer, sources)

    reply, record = llm.structured(
        "describe",
        "describe",
        {"question": question, "documentation": documentation, "history": list(history or [])},
        DescribeReply,
        counters=counters,
        validate=validate,
        node="describe_from_metadata",
    )
    return reply, record
