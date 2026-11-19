"""`extract_query_intent` (design document Section 5, Phase C).

The LLM reads the question into a `QueryIntent` using only what retrieval returned. Code then
rejects any dataset, indicator or category value that was not retrieved; a rejected reply is
retried once with the same prompt, then the node fails with `backend_error`.

`retrieved` is the retrieval output for this question, as a mapping:

    {"tables": [{"dataset_id", "title", "geo_levels", "coverage_start", "coverage_end",
                 "period_types", "caveats"}, ...],
     "indicators": [{"dataset_id", "indicator_id", "label", "unit"}, ...],
     "categories": {dataset_id: {column: [values shown to the model]}},
     "cards": [str, ...]}
"""

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import BaseModel

from analyst.contracts.intent import QueryIntent
from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient
from analyst.inference.prompts import PromptRegistry

NONE_FIT = "none_fit"
TABLE_FIELDS = (
    "dataset_id",
    "title",
    "geo_levels",
    "coverage_start",
    "coverage_end",
    "period_types",
    "caveats",
)


def context_payload(retrieved: Mapping[str, Any]) -> dict[str, Any]:
    """What the prompt shows inside <context>: retrieved tables, indicators, codelists, cards."""
    return {
        "datasets": [{k: t.get(k) for k in TABLE_FIELDS if k in t} for t in retrieved["tables"]],
        "indicators": [
            {k: i[k] for k in ("dataset_id", "indicator_id", "label", "unit") if k in i}
            for i in retrieved.get("indicators", [])
        ],
        "category_values": retrieved.get("categories", {}),
        "guidance": list(retrieved.get("cards", [])),
    }


def question_payload(retrieved: Mapping[str, Any]) -> dict[str, Any]:
    """The per-question part of intent prompts v5 and v6: candidate datasets, the category
    values shown for them, guidance cards and today's date (v6 declines "past month" when the
    data ends earlier). Indicators are in the fixed catalogue block, which stays cacheable."""
    payload = context_payload(retrieved)
    payload.pop("indicators")
    payload["today"] = retrieved.get("today") or date.today().isoformat()
    return payload


HASH_SUFFIX = re.compile(r"_([0-9a-f]{8})$")


def repair_indicator_ids(intent: QueryIntent, retrieved: Mapping[str, Any]) -> QueryIntent:
    """Replace a miscopied indicator id by the one valid id of the chosen dataset with the same
    hash suffix. Catalogue ids end in an 8-character hash of the source label, so the suffix
    identifies the indicator even when the words before it were copied wrongly (dev ladder,
    19 Nov: "..._who_received_bcg_4564c661" for "..._who_have_received_bcg_4564c661"). An id
    without a unique match is left as it is, for validation to reject."""
    valid = [
        str(i["indicator_id"])
        for i in retrieved.get("indicators", [])
        if i.get("dataset_id") == intent.dataset_id
    ]
    if not valid or all(i in valid for i in intent.indicator_ids):
        return intent
    by_hash: dict[str, list[str]] = {}
    for v in valid:
        match = HASH_SUFFIX.search(v)
        if match:
            by_hash.setdefault(match.group(1), []).append(v)
    fixed = []
    for given in intent.indicator_ids:
        match = HASH_SUFFIX.search(given)
        candidates = by_hash.get(match.group(1), []) if match and given not in valid else []
        fixed.append(candidates[0] if len(candidates) == 1 else given)
    return intent.model_copy(update={"indicator_ids": fixed})


def check_intent(intent: QueryIntent, retrieved: Mapping[str, Any]) -> None:
    """Raise `ValueError` when the intent uses a value retrieval did not return."""
    datasets = {t["dataset_id"] for t in retrieved["tables"]}
    if intent.dataset_id != NONE_FIT and intent.dataset_id not in datasets:
        raise ValueError(f"dataset_id {intent.dataset_id!r} was not retrieved")
    if intent.action == "answer" and intent.dataset_id == NONE_FIT:
        raise ValueError("action 'answer' needs a retrieved dataset_id")
    indicators = {
        i["indicator_id"]
        for i in retrieved.get("indicators", [])
        if i["dataset_id"] == intent.dataset_id
    }
    unknown = [i for i in intent.indicator_ids if i not in indicators]
    if unknown:
        raise ValueError(f"indicator_ids {unknown} are not indicators of {intent.dataset_id}")
    if intent.action == "answer" and not intent.indicator_ids:
        raise ValueError("action 'answer' needs at least one indicator_id")
    codelists = retrieved.get("categories", {}).get(intent.dataset_id, {})
    for column, values in intent.categories.items():
        shown = codelists.get(column)
        if not isinstance(shown, list):  # only value lists shown to the model count
            raise ValueError(f"category column {column!r} is not listed for {intent.dataset_id}")
        bad = [v for v in values if v not in shown]
        if bad:
            raise ValueError(f"values {bad} are not in the codelist of {column!r}")
    if intent.action in {"clarify", "decline"} and not intent.reason:
        raise ValueError(f"action {intent.action!r} needs a reason")


STANDALONE_MAX_CHARS = 300  # a longer "standalone question" is reasoning, not a question


def _tidy(intent: QueryIntent, retrieved: Mapping[str, Any]) -> QueryIntent:
    """Code-side clean-up that never costs a retry: an invalid table pointer is dropped, and so
    is a standalone question that holds the model's reasoning (UI test, 18 Nov: 856 characters
    beginning "Now show monsoon rainfall ... Wait, the user asked ...")."""
    intent = _checked_pointer(repair_indicator_ids(intent, retrieved), retrieved)
    text = intent.standalone_question
    if text is not None and (len(text) > STANDALONE_MAX_CHARS or "\n" in text.strip()):
        intent = intent.model_copy(update={"standalone_question": None})
    return intent


def _checked_pointer(intent: QueryIntent, retrieved: Mapping[str, Any]) -> QueryIntent:
    """Keep `catalogue_dataset_id` only when it names a catalogue dataset that is not already a
    candidate; otherwise drop it. A wrong pointer costs nothing (no retry, no widened search)."""
    pointer = intent.catalogue_dataset_id
    if pointer is None:
        return intent
    block = retrieved.get("catalogue_block") or {}
    known = {str(d.get("dataset_id")) for d in block.get("datasets", []) if isinstance(d, dict)}
    candidates = {str(t.get("dataset_id")) for t in retrieved.get("tables", [])}
    if pointer in known and pointer not in candidates:
        return intent
    return intent.model_copy(update={"catalogue_dataset_id": None})


def extract_intent(
    question: str,
    retrieved: Mapping[str, Any],
    prior_plan: BaseModel | Mapping[str, Any] | None,
    llm: LlmClient,
    counters: CallCounter,
    history: list[dict[str, Any]] | None = None,
) -> tuple[QueryIntent, LlmCallRecord]:
    prior = prior_plan.model_dump(mode="json") if isinstance(prior_plan, BaseModel) else prior_plan
    variables: dict[str, Any] = {
        # Fixed for a catalogue release, so the long prefix is cached by the provider.
        "catalogue": retrieved.get("catalogue_block") or {},
        "question": question,
        "context": question_payload(retrieved),
        "prior_plan": prior,
    }
    if "history" in (getattr(llm, "registry", None) or PromptRegistry()).get("intent").inputs:
        variables["history"] = history or []  # intent v7: the last turns, oldest first
    parsed, record = llm.structured(
        "intent",
        "intent",
        variables,
        QueryIntent,
        counters=counters,
        validate=lambda intent: check_intent(repair_indicator_ids(intent, retrieved), retrieved),
        node="extract_query_intent",
    )
    return _tidy(parsed, retrieved), record
