from datetime import datetime, timezone
from pydantic import Field
from .common import Contract
class Event(Contract):
    stage: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, object] = Field(default_factory=dict)
