"""Clarifying-question text (design document Section 5, `ask_clarification`).

The slot and the options are decided by code (the plan's `unresolved` entries); the LLM only
words one question. A question that introduces a number found neither in the user's message nor
in the options is rejected and retried once.
"""

import re

from pydantic import BaseModel, ConfigDict

from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient

MAX_CHARS = 300
_NUMBER = re.compile(r"\d+(?:[.,-]\d+)*")


class Clarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str


def check_question(text: str, question: str, options: list[str]) -> None:
    if not text.strip() or len(text) > MAX_CHARS:
        raise ValueError(f"the question must be 1-{MAX_CHARS} characters")
    allowed = set(_NUMBER.findall(question)) | {n for o in options for n in _NUMBER.findall(o)}
    invented = [n for n in _NUMBER.findall(text) if n not in allowed]
    if invented:
        raise ValueError(f"numbers {invented} are not in the message or the options")


def write_clarification(
    question: str, slot: str, options: list[str], llm: LlmClient, counters: CallCounter
) -> tuple[str, LlmCallRecord]:
    reply, record = llm.structured(
        "clarify",
        "clarify",
        {"question": question, "slot": slot, "options": options},
        Clarification,
        counters=counters,
        validate=lambda c: check_question(c.question, question, options),
        node="ask_clarification",
    )
    return reply.question.strip(), record
