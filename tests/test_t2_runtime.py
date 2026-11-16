from __future__ import annotations
from pathlib import Path
from analyst.agents.memory import ConversationMemory
from analyst.agents.runlog import RunLogger
from analyst.contracts.evidence import EvidenceBundle
from analyst.tools.charts import select_chart
from analyst.tools.evidence import EvidenceStore, build_evidence, is_current

def test_chart_uses_result_rows() -> None:
    spec = select_chart([{"month": "Jan", "rainfall": 10.0}, {"month": "Feb", "rainfall": 12.0}])
    assert spec.chart_type == "bar"
    assert spec.specification["encoding"]["y"]["field"] == "rainfall"

def test_evidence_store_round_trip(tmp_path: Path) -> None:
    bundle = build_evidence(dataset_id="rain", dataset_version="v1", sql="SELECT 1",
                            rows=[{"value": 1}])
    store = EvidenceStore(tmp_path / "evidence.sqlite")
    assert store.put(bundle) == bundle.evidence_id
    loaded = store.get(bundle.evidence_id)
    assert loaded is not None
    assert loaded.rows[0]["value"] == 1
    assert is_current(loaded, {"rain": "v1"})
    assert not is_current(loaded, {"rain": "v2"})

def test_memory_persists_pending_clarification(tmp_path: Path) -> None:
    memory = ConversationMemory(tmp_path / "memory.sqlite")
    memory.save("c1", pending_clarification={"question": "Which state?", "options": ["UP", "Bihar"]})
    assert memory.get("c1")["pending_clarification"]["question"] == "Which state?"

def test_run_logger_writes_run(tmp_path: Path) -> None:
    logger = RunLogger(tmp_path / "runs.sqlite")
    logger.write_state({
        "run_id": "r1", "conversation_id": "c1", "question": "test",
        "config": {"version": "v0", "config_hashes": {}}, "started_at": "2026-11-16T00:00:00Z",
        "outcome": "declined", "outcome_cause": "not_covered", "events": [], "decision_log": [], "sql": []
    })
    import sqlite3
    with sqlite3.connect(tmp_path / "runs.sqlite") as db:
        row = db.execute("SELECT outcome,cause FROM runs WHERE run_id='r1'").fetchone()
    assert row == ("declined", "not_covered")
