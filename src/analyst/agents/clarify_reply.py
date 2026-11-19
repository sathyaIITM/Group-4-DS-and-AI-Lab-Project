"""Read a reply to a clarification question before any model sees it.

Short replies such as "second one", "2", "yes", "rural" or "neither" carry no meaning on their
own: the router (Kev or Jev) and the intent model would see a fragment. Code maps the reply onto
the options it offered and writes one complete question for every later node, so the decision
models always receive the same kind of input as a first question.

Outcomes:
- `option`: the reply picks one offered option (by position, by its words, or "yes" when only
  one option was offered).
- `all`: "all", "both", "all of them": every offered option.
- `none`: the reply rejects every option ("no", "neither", "none of these").
- `new_question`: the reply is a new, self-contained question; the clarification is dropped.
- `free`: anything else ("the one for women"); the reply is passed on with the options listed,
  for the intent model to read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from analyst.contracts import Clarification

Kind = Literal["option", "all", "none", "new_question", "free"]

ORDINALS = {
    "first": 0,
    "1st": 0,
    "one": 0,
    "1": 0,
    "former": 0,
    "pehla": 0,
    "second": 1,
    "2nd": 1,
    "two": 1,
    "2": 1,
    "dusra": 1,
    "doosra": 1,
    "third": 2,
    "3rd": 2,
    "three": 2,
    "3": 2,
    "fourth": 3,
    "4th": 3,
    "four": 3,
    "4": 3,
    "fifth": 4,
    "5th": 4,
    "five": 4,
    "5": 4,
    "sixth": 5,
    "6th": 5,
    "six": 5,
    "6": 5,
}
LAST_WORDS = {"last", "latter", "final"}
YES_WORDS = {
    "yes",
    "y",
    "yeah",
    "yep",
    "ok",
    "okay",
    "sure",
    "correct",
    "right",
    "haan",
    "ha",
    "ji",
}
ALL_WORDS = {"all", "both", "every", "everything", "each", "sab", "dono"}
NO_WORDS = {"no", "nope", "neither", "none", "nahi", "nahin", "cancel", "nothing"}
FILLER = {"the", "a", "an", "option", "one", "please", "i", "mean", "want", "that", "is", "it"}
QUESTION_START = re.compile(
    r"^(what|which|how|show|list|compare|give|tell|is|are|was|were|did|does|when|where|who)\b"
)
NEW_QUESTION_WORDS = 6  # an unmatched reply this long is read as a new question
SHORT_REPLY_WORDS = 4  # an option named inside a reply counts only in a reply this short


@dataclass(frozen=True)
class ReplyReading:
    """How a clarification reply was read: its kind, chosen option and full question."""

    kind: Kind
    option: str | None
    question: str  # the complete question every later node receives


def _words(text: str) -> list[str]:
    """Split text into lower-case words and numbers."""
    return re.findall(r"[a-z0-9+]+", text.casefold())


def _by_position(words: list[str], options: list[str]) -> str | None:
    """Return the option a short positional reply picks ("second", "2", "last"), if any."""
    if not options:
        return None
    content = [w for w in words if w not in FILLER]
    if len(content) > 2:  # "the second state you listed" is not a bare position
        return None
    for word in content:
        if word in LAST_WORDS:
            return options[-1]
        if word in ORDINALS and ORDINALS[word] < len(options):
            return options[ORDINALS[word]]
    return None


def _by_words(reply: str, options: list[str]) -> str | None:
    """The one option the reply names: equal text, or every reply word found in the option."""
    words = [w for w in _words(reply) if w not in FILLER]
    if not words:
        return None
    exact = [o for o in options if _words(o) == _words(reply)]
    if len(exact) == 1:
        return exact[0]
    found = [o for o in options if all(w in _words(o) for w in words)]
    if len(found) == 1:
        return found[0]
    if len(words) > SHORT_REPLY_WORDS:  # a long reply is not read as naming an option
        return None
    inside = [o for o in options if " ".join(_words(o)) in " ".join(_words(reply))]
    return inside[0] if len(inside) == 1 else None


def read_reply(reply: str, pending: Clarification) -> ReplyReading:
    """Map a clarification reply onto the offered options; see the module docstring."""
    words = _words(reply)
    options = list(pending.options)
    original = pending.original_question
    asked = pending.question or "A detail was missing."

    def merged(answer: str) -> str:
        """Join the original question, the clarification asked and the user's answer."""
        return f"{original}\nClarification asked: {asked}\nAnswer: {answer}"

    chosen = _by_position(words, options) or _by_words(reply, options)
    if chosen is None and words and set(words) <= YES_WORDS and len(options) == 1:
        chosen = options[0]
    if chosen is not None:
        return ReplyReading("option", chosen, merged(chosen))
    filler = FILLER | {"of", "these", "them", "options", "the"}
    if options and words and set(words) & ALL_WORDS and set(words) <= ALL_WORDS | filler:
        return ReplyReading("all", None, merged(f"all of these ({'; '.join(options)})"))
    if words and set(words) <= NO_WORDS | FILLER | {"of", "these", "them", "both"}:
        offered = "; ".join(options) if options else "the offered reading"
        return ReplyReading("none", None, merged(f"none of these ({offered})"))
    text = reply.strip()
    if len(words) >= NEW_QUESTION_WORDS or (QUESTION_START.match(text.casefold()) and "?" in text):
        return ReplyReading("new_question", None, text)
    listed = f" (options offered: {'; '.join(options)})" if options else ""
    return ReplyReading("free", None, merged(f"{text}{listed}"))
