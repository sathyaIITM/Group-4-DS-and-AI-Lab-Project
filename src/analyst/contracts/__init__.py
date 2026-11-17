"""Shared contracts (design document Section 4), with the T2 additions in `runtime.py`."""

from analyst.contracts.chart import ChartSpec, ChartType
from analyst.contracts.checks import CheckOutcome, CheckReport, FailureClass, NumberCheck
from analyst.contracts.common import (
    Assumption,
    Caveat,
    CellRef,
    Contract,
    GeoLevel,
    IndicatorRef,
    PeriodType,
    PeriodWindow,
    Place,
    QualityFlag,
)
from analyst.contracts.coverage import CoverageResult, MissingPart
from analyst.contracts.decisions import DecisionRecord, RoutingDecision
from analyst.contracts.events import Event, EventType
from analyst.contracts.evidence import (
    ConfidenceResult,
    EvidenceBundle,
    SourceRef,
    VerificationResult,
)
from analyst.contracts.intent import DerivationOp, DerivationRequest, Operation, QueryIntent
from analyst.contracts.narration import Claim, Narration, NumberRef
from analyst.contracts.plan import InterpretationPlan, UnresolvedSlot
from analyst.contracts.response import AgentResponse, Cause, Outcome
from analyst.contracts.results import ColumnSpec, DerivedValue, QueryResult
from analyst.contracts.runtime import Clarification, RetryHint, ScreenResult
from analyst.contracts.sql import SqlAttempt, SqlDraft

CONTRACT_VERSION = "1.0"

__all__ = [
    "CONTRACT_VERSION",
    "AgentResponse",
    "Assumption",
    "Cause",
    "Caveat",
    "CellRef",
    "ChartSpec",
    "ChartType",
    "CheckOutcome",
    "CheckReport",
    "Claim",
    "Clarification",
    "ColumnSpec",
    "ConfidenceResult",
    "Contract",
    "CoverageResult",
    "DecisionRecord",
    "DerivationOp",
    "DerivationRequest",
    "DerivedValue",
    "Event",
    "EventType",
    "EvidenceBundle",
    "FailureClass",
    "GeoLevel",
    "IndicatorRef",
    "InterpretationPlan",
    "MissingPart",
    "Narration",
    "NumberCheck",
    "NumberRef",
    "Operation",
    "Outcome",
    "PeriodType",
    "PeriodWindow",
    "Place",
    "QualityFlag",
    "QueryIntent",
    "QueryResult",
    "RetryHint",
    "RoutingDecision",
    "ScreenResult",
    "SourceRef",
    "SqlAttempt",
    "SqlDraft",
    "UnresolvedSlot",
    "VerificationResult",
]
