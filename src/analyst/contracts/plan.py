from __future__ import annotations
from pydantic import Field
from .common import Contract, Place, PeriodWindow

class InterpretationPlan(Contract):
    dataset_id: str | None = None
    indicator_id: str | None = None
    places: tuple[Place, ...] = ()
    periods: tuple[PeriodWindow, ...] = ()
    geography: dict[str, str] = Field(default_factory=dict)
    period: dict[str, str] = Field(default_factory=dict)
    unit: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    derivations: tuple[dict[str, str], ...] = ()
    assumptions: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
