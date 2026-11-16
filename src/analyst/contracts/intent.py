"""Query intent (design document Section 4.2): written by the LLM, validated by code."""

from typing import Literal

from analyst.contracts.common import Contract, GeoLevel

Operation = Literal[
    "lookup", "ranking", "change", "trend", "aggregate", "comparison", "share", "list"
]
DerivationOp = Literal[
    "pct_change",
    "change_pp",
    "cagr",
    "share",
    "per_capita",
    "inflation_from_index",
    "rank",
    "mean",
    "weighted_mean",
    "difference",
]


class DerivationRequest(Contract):
    op: DerivationOp
    args: dict[str, str]


class QueryIntent(Contract):
    action: Literal["answer", "clarify", "decline"]
    dataset_id: str
    indicator_ids: list[str]
    place_mentions: list[str]
    all_places_level: GeoLevel | None
    period_mentions: list[str]
    categories: dict[str, list[str]]
    operation: Operation
    order: Literal["asc", "desc"] | None
    limit: int | None
    derivations: list[DerivationRequest]
    changed_slots: list[str]
    reason: str | None
