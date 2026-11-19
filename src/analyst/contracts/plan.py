"""Interpretation plan (design document Section 4.2): written by code only."""

from typing import Literal

from analyst.contracts.common import (
    Assumption,
    Contract,
    GeoLevel,
    IndicatorRef,
    PeriodWindow,
    Place,
)
from analyst.contracts.intent import DerivationRequest, Operation


class UnresolvedSlot(Contract):
    """A slot that could not be resolved, with the user's mention and the options to offer."""

    slot: Literal["place", "period", "indicator", "category", "geo_level"]
    mention: str
    options: list[str]


class InterpretationPlan(Contract):
    """The resolved query plan: table, indicators, places, periods, categories and operation."""

    dataset_id: str
    obs_table: str
    dataset_version: str
    indicators: list[IndicatorRef]
    places: list[Place]
    all_places_level: GeoLevel | None
    periods: list[PeriodWindow]
    categories: dict[str, list[str]]
    operation: Operation
    order: Literal["asc", "desc"] | None
    limit: int | None
    derivations: list[DerivationRequest]
    exclude_total_rows: bool
    assumptions: list[Assumption]
    unresolved: list[UnresolvedSlot]
