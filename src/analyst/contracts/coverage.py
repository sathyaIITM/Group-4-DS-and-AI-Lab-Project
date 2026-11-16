from typing import Literal
from .common import Contract
class CoverageResult(Contract):
    status: Literal["covered", "partial", "ambiguous", "not_covered"] = "covered"
    probability: float = 1.0
    decided_by: str = "rules"
    missing_parts: tuple[str, ...] = ()
    supported_scope: str | None = None
