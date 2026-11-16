from pydantic import Field
from .common import Contract
class EvidenceBundle(Contract):
    evidence_id: str
    dataset_id: str | None = None
    dataset_version: str | None = None
    sql: str | None = None
    rows: tuple[dict[str, object], ...] = ()
    caveats: tuple[str, ...] = ()
    source: str | None = None
    config_hash: str | None = None
