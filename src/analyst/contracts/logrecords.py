from pydantic import Field

from .common import Contract


class RunRecord(Contract):
    run_id: str
    conversation_id: str
    question: str
    version: str
    outcome: str | None = None
    cause: str | None = None
    started_at: str
    finished_at: str
    git_sha: str = "unknown"
    config_hash: str = ""


class NodeEventRecord(Contract):
    run_id: str
    stage: str
    timestamp: str
    details: dict[str, object] = Field(default_factory=dict)
