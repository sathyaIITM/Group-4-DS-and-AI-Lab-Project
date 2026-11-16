from __future__ import annotations
from pydantic import Field
from .common import Contract

class QueryIntent(Contract):
    dataset_id: str | None = None
    indicator_id: str | None = None
    place_mentions: tuple[str, ...] = ()
    period_mentions: tuple[str, ...] = ()
    categories: dict[str, str] = Field(default_factory=dict)
    derivations: tuple[dict[str, str], ...] = ()
    changed_slots: tuple[str, ...] = ()
