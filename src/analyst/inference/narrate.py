"""`narrate_from_result_only` (design document Section 5, Phase G).

The LLM writes the answer from the evidence bundle and returns each claim with the source of
every number in it: a result cell or a derived value. Code rejects a reply whose references
point outside the evidence (and retries once). Whether each number matches its source is the
deterministic number check of the next node.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from analyst.contracts.narration import Claim, Narration
from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient


class NarrationReply(BaseModel):
    """The LLM's part of a `Narration`; `attempt` is set by code."""

    model_config = ConfigDict(extra="forbid")

    text: str
    claims: list[Claim]


def _evidence_dict(evidence: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    return evidence.model_dump(mode="json") if isinstance(evidence, BaseModel) else dict(evidence)


MONTHS = "January February March April May June July August September October November December"
YEAR_KINDS = {1: "calendar year", 4: "fiscal year", 7: "July-June survey year"}


def describe_period(window: Mapping[str, Any]) -> str | None:
    """Plain words for a yearly window, chosen by its start month: the data contract types every
    year that does not start in January as `survey_year`, so per capita GSDP (April to March)
    was narrated as a "survey year" (dev run 3, e2e-066)."""
    kind = str(window.get("type", ""))
    if kind not in {"calendar_year", "survey_year", "fiscal_year", "agri_year"}:
        return None
    start, end = str(window.get("start", "")), str(window.get("end", ""))
    if len(start) < 7 or len(end) < 7:
        return None
    names = MONTHS.split()
    first, last = int(start[5:7]), int(end[5:7])
    words = YEAR_KINDS.get(first, "year")
    if kind == "agri_year":
        words = "agricultural year"
    return f"{words}, {names[first - 1]} {start[:4]} to {names[last - 1]} {end[:4]}"


def _with_period_words(bundle: dict[str, Any]) -> dict[str, Any]:
    plan = bundle.get("plan")
    if not isinstance(plan, dict):
        return bundle
    periods = []
    for window in plan.get("periods") or []:
        words = describe_period(window) if isinstance(window, dict) else None
        periods.append({**window, "description": words} if words else window)
    return {**bundle, "plan": {**plan, "periods": periods}}


def check_references(reply: NarrationReply, evidence: Mapping[str, Any]) -> None:
    result = evidence.get("result") or {}
    columns = {c["name"] for c in result.get("columns", [])}
    n_rows = len(result.get("rows", []))
    derived = {d["id"] for d in evidence.get("derived", [])}
    if not reply.text.strip():
        raise ValueError("empty answer")
    for claim in reply.claims:
        for number in claim.numbers:
            if (number.cell is None) == (number.derived_id is None):
                raise ValueError(f"number {number.text!r}: set exactly one of cell, derived_id")
            if number.cell is not None and (
                not 0 <= number.cell.row < n_rows or number.cell.column not in columns
            ):
                raise ValueError(f"number {number.text!r}: cell {number.cell} is not in the result")
            if number.derived_id is not None and number.derived_id not in derived:
                raise ValueError(f"number {number.text!r}: no derived value {number.derived_id}")


def narrate(
    evidence: BaseModel | Mapping[str, Any],
    hints: list[str] | None,
    llm: LlmClient,
    counters: CallCounter,
    attempt: int = 1,
    question: str | None = None,
) -> tuple[Narration, LlmCallRecord]:
    """`question` replaces the bundle's question when the intent rewrote a follow-up as a
    standalone question ("And Maharashtra?" -> "Unemployment rate in Maharashtra, 2021-22")."""
    bundle = _with_period_words(_evidence_dict(evidence))
    asked = question or bundle.get("question", "")
    reply, record = llm.structured(
        "narrate",
        "narrate",
        {"question": asked, "evidence": bundle, "hints": hints or None},
        NarrationReply,
        counters=counters,
        validate=lambda r: check_references(r, bundle),
        node="narrate_from_result_only",
    )
    return Narration(attempt=attempt, text=reply.text, claims=reply.claims), record
