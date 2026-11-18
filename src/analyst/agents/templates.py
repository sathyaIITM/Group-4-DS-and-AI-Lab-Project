"""Fixed response texts for non-answer outcomes (design document Section 5, terminal nodes).

The wording is reviewed by T1 (milestone 4 brief, task H).
"""

from __future__ import annotations

from analyst.contracts import Cause, MissingPart

SCREEN_REASONS = {
    "empty_request": "The request is empty.",
    "input_too_long": "The request is too long to process.",
    "unsafe_instruction": "The request contains an instruction that cannot be followed.",
}

ABSTAIN = {
    "no_rows": (
        "The query returned no rows for the requested places and periods; no figure is given."
    ),
    "unverified": (
        "The figures in the draft answer do not match the query result; no answer is given."
    ),
    "low_confidence": (
        "The confidence in the answer is below the required level; no answer is given."
    ),
    "deadline_exceeded": "The request exceeded the time limit before an answer could be verified.",
    "verifier_unavailable": "The answer could not be verified because the verifier is unavailable.",
    "not_comparable": "The requested parts cannot be compared in one answer.",
}

FAILURE = {
    "sql_invalid": "No valid query could be produced after the permitted repairs.",
    "execution_error": "The query could not be executed after the permitted attempts.",
    "result_check_failed": (
        "The result failed the consistency checks after the permitted attempts."
    ),
    "budget_exhausted": (
        "The limit on model calls for one request was reached before the answer was complete."
    ),
    "backend_error": "An internal service did not respond correctly.",
}


def out_of_scope(reason: str | None) -> str:
    return SCREEN_REASONS.get(reason or "", "The request cannot be processed.")


def decline(missing: list[MissingPart], pointers: list[str]) -> str:
    text = "The catalogue does not contain the requested data."
    if missing:
        text += " Missing: " + "; ".join(f"{m.kind} ({m.detail})" for m in missing) + "."
    if pointers:
        text += " Related tables: " + ", ".join(pointers) + "."
    return text + " The request has been recorded as a data request."


def abstain(cause: Cause) -> str:
    return ABSTAIN.get(cause, "No answer is given.")


def failure(cause: Cause) -> str:
    return FAILURE.get(cause, FAILURE["backend_error"])


def clarification(question: str | None, options: list[str]) -> str:
    text = question or "Please state the place, the period and the indicator."
    if options:  # numbered, so that "the second one" or "2" maps onto an option
        text += " Options: " + "; ".join(f"{n}. {o}" for n, o in enumerate(options, 1)) + "."
    return text
