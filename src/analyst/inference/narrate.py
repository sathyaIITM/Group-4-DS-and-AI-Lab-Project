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
) -> tuple[Narration, LlmCallRecord]:
    bundle = _evidence_dict(evidence)
    reply, record = llm.structured(
        "narrate",
        "narrate",
        {"question": bundle.get("question", ""), "evidence": bundle, "hints": hints or None},
        NarrationReply,
        counters=counters,
        validate=lambda r: check_references(r, bundle),
        node="narrate_from_result_only",
    )
    return Narration(attempt=attempt, text=reply.text, claims=reply.claims), record
