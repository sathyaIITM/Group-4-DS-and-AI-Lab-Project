from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4
from analyst.contracts.evidence import EvidenceBundle

class EvidenceStore:
    """Persistent evidence bundles keyed by opaque evidence ID."""
    def __init__(self, path: str | Path = "outputs/runs/evidence.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS evidence (evidence_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    def put(self, bundle: EvidenceBundle) -> str:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO evidence VALUES (?,?)",
                       (bundle.evidence_id, bundle.model_dump_json()))
        return bundle.evidence_id
    def get(self, evidence_id: str) -> EvidenceBundle | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT payload FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
        return EvidenceBundle.model_validate_json(row[0]) if row else None

def build_evidence(*, dataset_id: str, dataset_version: str, sql: str,
                   rows: list[dict[str, Any]], caveats: list[str] | None = None,
                   source: str | None = None, config_hash: str | None = None) -> EvidenceBundle:
    return EvidenceBundle(evidence_id=str(uuid4()), dataset_id=dataset_id,
        dataset_version=dataset_version, sql=sql, rows=tuple(rows),
        caveats=tuple(caveats or []), source=source, config_hash=config_hash)

def is_current(bundle: EvidenceBundle, live_versions: dict[str, str]) -> bool:
    return bool(bundle.dataset_id and bundle.dataset_version and
                live_versions.get(bundle.dataset_id) == bundle.dataset_version)
