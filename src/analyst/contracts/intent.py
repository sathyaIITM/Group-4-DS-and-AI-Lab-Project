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
    """A calculation the question asks for (change, share, ratio and so on) and its arguments."""

    op: DerivationOp
    args: dict[str, str]


class QueryIntent(Contract):
    """What the question asks for, extracted by the model before places and periods are resolved."""

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
    # Added in intent prompt v2: the slot a "clarify" intent asks about (None otherwise).
    missing_slot: Literal["place", "period", "indicator", "category", "geo_level"] | None = None
    # Added in intent prompt v7 (conversation history). `follow_up`: the question continues the
    # previous turn, so slots it does not name carry over; False for a new topic, None when the
    # prompt does not say (older prompts: carry over as before). `standalone_question`: the
    # question rewritten with references to earlier turns resolved ("And Maharashtra?" ->
    # "Unemployment rate in Maharashtra in 2021-22"); narration and the evidence report use it.
    follow_up: bool | None = None
    standalone_question: str | None = None
    # Intent v7: the dataset in the full catalogue that holds the measure when none of the
    # retrieved candidates does. Only then does a not-covered result widen the search, and the
    # widened search adds exactly this table (dev run 3: 5 of 6 widened searches were wasted).
    catalogue_dataset_id: str | None = None
