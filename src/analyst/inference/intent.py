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

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from analyst.contracts.intent import QueryIntent
from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient

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
    """The per-question part of intent prompt v5: candidate datasets, the category values
    shown for them and guidance cards. Indicators are in the fixed catalogue block."""
    payload = context_payload(retrieved)
    payload.pop("indicators")
    return payload


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


def extract_intent(
    question: str,
    retrieved: Mapping[str, Any],
    prior_plan: BaseModel | Mapping[str, Any] | None,
    llm: LlmClient,
    counters: CallCounter,
) -> tuple[QueryIntent, LlmCallRecord]:
    prior = prior_plan.model_dump(mode="json") if isinstance(prior_plan, BaseModel) else prior_plan
    return llm.structured(
        "intent",
        "intent",
        {
            # Fixed for a catalogue release, so the long prefix is cached by the provider.
            "catalogue": retrieved.get("catalogue_block") or {},
            "question": question,
            "context": question_payload(retrieved),
            "prior_plan": prior,
        },
        QueryIntent,
        counters=counters,
        validate=lambda intent: check_intent(intent, retrieved),
        node="extract_query_intent",
    )
