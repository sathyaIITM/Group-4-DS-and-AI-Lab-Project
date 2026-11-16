from pydantic import Field
from .common import Contract
class CheckReport(Contract):
    status: str = "pass"
    checks: dict[str, bool | str | float] = Field(default_factory=dict)
    failures: tuple[str, ...] = ()
class VerificationResult(Contract):
    number_check: str = "match"
    claims_supported: bool = True
    intent_aligned: bool = True
    unsupported_claims: tuple[str, ...] = ()
    misaligned_slots: tuple[str, ...] = ()
    score: float = 1.0
