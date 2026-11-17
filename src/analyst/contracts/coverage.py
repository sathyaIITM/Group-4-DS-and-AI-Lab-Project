"""Coverage (design document Section 4.3)."""

from typing import Literal

from analyst.contracts.common import Contract
from analyst.contracts.plan import InterpretationPlan


class MissingPart(Contract):
    kind: Literal[
        "indicator",
        "period",
        "place",
        "geo_level",
        "population",
        "category",
        "derivation_input",
        "definition",
    ]
    detail: str


class CoverageResult(Contract):
    status: Literal["covered", "partial", "ambiguous", "not_covered"]
    probability: float | None
    decided_by: Literal["rules", "jev", "llm"]
    missing: list[MissingPart]
    supported_plan: InterpretationPlan | None
    left_out: list[str]
    pointers: list[str]
