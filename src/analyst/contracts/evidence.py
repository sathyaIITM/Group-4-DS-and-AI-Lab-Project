"""Evidence, verification and confidence (design document Section 4.6)."""

from datetime import datetime
from typing import Literal

from analyst.contracts.checks import CheckReport, NumberCheck
from analyst.contracts.common import Assumption, Caveat, Contract
from analyst.contracts.plan import InterpretationPlan
from analyst.contracts.results import DerivedValue, QueryResult


class SourceRef(Contract):
    """The published source of a table: title, publisher, licence and version."""

    dataset_id: str
    title: str
    publisher: str
    source_table: str
    licence: str
    retrieved: str
    dataset_version: str
    raw_sha256: str


class EvidenceBundle(Contract):
    """Everything needed to trace an answer: plan, sources, SQL, result, derivations and checks."""

    evidence_id: str
    run_id: str
    question: str
    plan: InterpretationPlan
    sources: list[SourceRef]
    sql: str
    statement: str
    result: QueryResult
    derived: list[DerivedValue]
    checks: CheckReport
    assumptions: list[Assumption]
    caveats: list[Caveat]
    config_digest: str
    contract_version: str
    created_at: datetime


class VerificationResult(Contract):
    """Outcome of verifying a narrated answer against its evidence."""

    numbers: NumberCheck
    claims_supported: bool | None
    unsupported_claims: list[str]
    intent_aligned: bool | None
    misaligned_slots: list[str]
    score: float | None
    skipped_reason: str | None


class ConfidenceResult(Contract):
    """The confidence badge shown with an answer and the inputs it was computed from."""

    probability: float | None
    badge: Literal["not_verified", "verified", "verified_with_caveats"]
    inputs: dict[str, float]
