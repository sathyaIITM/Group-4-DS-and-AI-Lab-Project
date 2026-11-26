"""Clarifying-question text (design document Section 5, `ask_clarification`).

The slot and the options are decided by code (the plan's `unresolved` entries); the LLM only
words one question. A question that introduces a number found neither in the user's message nor
in the options is rejected and retried once.
"""

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient

MAX_CHARS = 300
_NUMBER = re.compile(r"\d+(?:[.,-]\d+)*")


class Clarification(BaseModel):
    """The clarification question written by the model."""

    model_config = ConfigDict(extra="forbid")

    question: str


# The word a clarification uses for the missing detail (rule sheet S, T2 fix C1): "Which
# commodity?", not "Which category?". Category columns by name; places by the table's level.
CATEGORY_WORDS = {
    "commodity_name": "commodity", "crop": "crop", "variety": "variety", "grade": "grade",
    "season": "season", "crop_season": "crop season", "sector": "sector", "area": "area",
}  # fmt: skip
LEVEL_WORDS = {
    "market": "market", "district": "district", "subdivision": "sub-division", "state": "State",
}  # fmt: skip
SLOT_WORDS = {
    "indicator": "measure", "period": "period", "place": "place",
    "geo_level": "level (State or district)", "category": "group",
}  # fmt: skip
_NOT_NAMED = re.compile(r"^([a-z_]+) was not named")


def slot_detail(slot: str, mention: str, table: Mapping[str, Any] | None) -> str:
    """The plain word for a missing slot: the category column (commodity, variety), the
    table's place level (market, district) or the slot's own name (period, measure)."""
    table = table or {}
    if slot == "category":
        named = _NOT_NAMED.match(mention)
        if named and named.group(1) in CATEGORY_WORDS:
            return CATEGORY_WORDS[named.group(1)]
        return "group"
    if slot == "place":
        levels = [str(level) for level in table.get("geo_levels") or []]
        finest = next((LEVEL_WORDS[lv] for lv in levels if lv in LEVEL_WORDS), None)
        return finest if finest and len(levels) == 1 else "place"
    return SLOT_WORDS.get(slot, slot)


def fixed_question(detail: str, slot: str, mention: str) -> str:
    """The clarification used when no model writes it; it always names the detail."""
    quoted = slot in {"place", "period"} and mention and len(mention) <= 40
    if quoted and "named" not in mention:
        return f"Which {detail} is meant by '{mention}'?"
    return f"Which {detail} do you mean?"


# Words that also name a detail: a period question may ask for the season or the year, a
# place question for the State or the market. "category" and "detail" are never enough.
DETAIL_WORDS = {
    "period": ("period", "year", "month", "season", "date", "when", "time"),
    "place": ("place", "where", "state", "district", "market", "sub-division", "location"),
    "measure": ("measure", "indicator", "rate", "statistic"),
    "group": ("group", "definition", "age", "population", "women", "men", "persons"),
    "level": ("level", "state", "district"),
}  # fmt: skip


def names_detail(text: str, detail: str) -> bool:
    """True when the question names the missing detail ("commodity", "sub-division", or for a
    period "season" or "year")."""
    head = detail.split()[0].casefold()
    words = DETAIL_WORDS.get(head, (head,))
    lower = text.casefold().replace("-", "")
    return any(word.replace("-", "") in lower for word in words)


def check_question(text: str, question: str, options: list[str], detail: str | None = None) -> None:
    """Check the clarification's length, that it adds no numbers absent from the inputs and
    that it names the missing detail."""
    if not text.strip() or len(text) > MAX_CHARS:
        raise ValueError(f"the question must be 1-{MAX_CHARS} characters")
    if detail and not names_detail(text, detail):
        raise ValueError(f"the question must name the missing detail ({detail})")
    allowed = set(_NUMBER.findall(question)) | {n for o in options for n in _NUMBER.findall(o)}
    invented = [n for n in _NUMBER.findall(text) if n not in allowed]
    if invented:
        raise ValueError(f"numbers {invented} are not in the message or the options")


def write_clarification(
    question: str,
    slot: str,
    options: list[str],
    llm: LlmClient,
    counters: CallCounter,
    detail: str | None = None,
) -> tuple[str, LlmCallRecord]:
    """Write a clarification question for a missing slot with the model. ``detail`` is the
    plain word for the slot (`slot_detail`); the question must name it."""
    reply, record = llm.structured(
        "clarify",
        "clarify",
        {"question": question, "slot": detail or slot, "options": options},
        Clarification,
        counters=counters,
        validate=lambda c: check_question(c.question, question, options, detail),
        node="ask_clarification",
    )
    return reply.question.strip(), record
