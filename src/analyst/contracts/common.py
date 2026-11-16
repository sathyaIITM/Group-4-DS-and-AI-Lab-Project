from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class Place(Contract):
    requested: str
    resolved: str | None = None
    code: str | None = None
    correction: str | None = None

class PeriodWindow(Contract):
    requested: str
    start: str | None = None
    end: str | None = None
    frequency: str | None = None

class ScreenResult(Contract):
    passes: bool = True
    reason: str | None = None

class Clarification(Contract):
    question: str
    options: tuple[str, ...] = ()

class RetryHint(Contract):
    stage: str
    reason: str
    change_required: str

class ConfidenceResult(Contract):
    probability: float | None = None
    badge_level: str = "not_verified"
    inputs_used: dict[str, float | str | bool] = Field(default_factory=dict)
