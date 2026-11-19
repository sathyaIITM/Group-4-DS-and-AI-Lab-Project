"""Evidence bundles and their store (design document Section 6.8)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from analyst.contracts import CONTRACT_VERSION, EvidenceBundle, SourceRef

if TYPE_CHECKING:
    from analyst.agents.state import AnalystState

CATALOGUE = Path("data/processed/catalogue.json")


class EvidenceStore:
    """Persistent evidence bundles keyed by evidence id."""

    def __init__(self, path: str | Path = "outputs/runs/evidence.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS evidence "
                "(evidence_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def put(self, bundle: EvidenceBundle) -> str:
        """Store an evidence bundle and return its id."""
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT OR REPLACE INTO evidence VALUES (?,?)",
                (bundle.evidence_id, bundle.model_dump_json()),
            )
        return bundle.evidence_id

    def get(self, evidence_id: str) -> EvidenceBundle | None:
        """Return a stored evidence bundle, or None."""
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT payload FROM evidence WHERE evidence_id=?", (evidence_id,)
            ).fetchone()
        return EvidenceBundle.model_validate_json(row[0]) if row else None


def load_catalogue(path: Path = CATALOGUE) -> dict[str, dict[str, Any]]:
    """Published catalogue tables by dataset id; empty when no release is present."""
    if not path.exists():
        return {}
    tables = json.loads(path.read_text(encoding="utf-8"))["tables"]
    return {t["dataset_id"]: t for t in tables}


def source_ref(dataset_id: str, catalogue: dict[str, dict[str, Any]]) -> SourceRef:
    """Return the source reference of a dataset from the catalogue."""
    table = catalogue.get(dataset_id, {})
    return SourceRef(
        dataset_id=dataset_id,
        title=str(table.get("title", dataset_id)),
        publisher=str(table.get("publisher", "unknown")),
        source_table=str(table.get("source_table", "unknown")),
        licence=str(table.get("licence", "unknown")),
        retrieved=str(table.get("retrieved", "unknown")),
        dataset_version=str(table.get("dataset_version", "unknown")),
        raw_sha256=str(table.get("raw_sha256", "unknown")),
    )


def config_digest(state: AnalystState) -> str:
    """Return the SHA-256 of the run configuration."""
    return hashlib.sha256(state.config.model_dump_json().encode()).hexdigest()


def build_evidence(
    state: AnalystState, catalogue: dict[str, dict[str, Any]] | None = None
) -> EvidenceBundle:
    """The evidence bundle of an executed query; needs `plan`, `result` and `checks`."""
    if state.plan is None or state.result is None or state.checks is None:
        msg = "build_evidence needs plan, result and checks"
        raise ValueError(msg)
    catalogue = load_catalogue() if catalogue is None else catalogue
    latest = state.sql[-1] if state.sql else None
    return EvidenceBundle(
        evidence_id=f"ev_{state.run_id}",
        run_id=state.run_id,
        question=state.question,
        plan=state.plan,
        sources=[source_ref(state.plan.dataset_id, catalogue)],
        sql=state.result.sql,
        statement=latest.statement if latest else "",
        result=state.result,
        derived=state.derived,
        checks=state.checks,
        assumptions=state.plan.assumptions,
        caveats=state.checks.caveats,
        config_digest=config_digest(state),
        contract_version=CONTRACT_VERSION,
        created_at=datetime.now(UTC),
    )


def is_current(bundle: EvidenceBundle, live_versions: dict[str, str]) -> bool:
    """True when every source still has the dataset version the bundle was built on."""
    return bool(bundle.sources) and all(
        live_versions.get(s.dataset_id) == s.dataset_version for s in bundle.sources
    )
