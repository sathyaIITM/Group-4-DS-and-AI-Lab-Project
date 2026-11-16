from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

DDL = """
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, question TEXT NOT NULL,
 version TEXT NOT NULL, outcome TEXT, cause TEXT, started_at TEXT NOT NULL,
 finished_at TEXT NOT NULL, git_sha TEXT, config_hash TEXT
);
CREATE TABLE IF NOT EXISTS node_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, stage TEXT NOT NULL,
 timestamp TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, decision TEXT NOT NULL,
 backend TEXT, label TEXT, probability REAL, escalated INTEGER
);
CREATE TABLE IF NOT EXISTS sql_attempts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, sql_text TEXT NOT NULL,
 validation TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS llm_calls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, purpose TEXT NOT NULL,
 model TEXT, prompt_hash TEXT, duration_ms REAL, input_tokens INTEGER, output_tokens INTEGER,
 status TEXT, error_type TEXT
);
CREATE TABLE IF NOT EXISTS retrievals (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, query TEXT NOT NULL,
 source TEXT, dataset_id TEXT, rank INTEGER, score REAL, widened INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checks (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, check_name TEXT NOT NULL,
 status TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, kind TEXT NOT NULL,
 artifact_id TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
 evidence_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, dataset_id TEXT,
 dataset_version TEXT, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, request_text TEXT NOT NULL,
 domain TEXT, status TEXT NOT NULL DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS feedback (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, rating TEXT,
 comment TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS memory (
 conversation_id TEXT PRIMARY KEY, pending_clarification TEXT, prior_plan TEXT,
 prior_sql TEXT, prior_result_ref TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

class RunLogger:
    """Buffered per-run SQLite writer. A run is committed in one transaction."""
    def __init__(self, path: str | Path = "outputs/runs/runs.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(DDL)

    def write_state(self, state: dict[str, Any]) -> None:
        def value(key: str, default: Any = None) -> Any:
            item = state.get(key, default)
            return item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        config = value("config", {}) or {}
        started = value("started_at")
        if isinstance(started, dict):
            started = started.get("isoformat", str(started))
        elif hasattr(started, "isoformat"):
            started = started.isoformat()
        else:
            started = str(started or datetime.now(timezone.utc).isoformat())
        finished = datetime.now(timezone.utc).isoformat()
        run_id = str(value("run_id", "unknown"))
        try:
            with sqlite3.connect(self.path) as db:
                with db:
                    db.execute("""INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                        run_id, value("conversation_id", ""), value("question", ""),
                        config.get("version", "v0") if isinstance(config, dict) else "v0",
                        value("outcome"), value("outcome_cause"), started, finished,
                        value("git_sha", "unknown"), json.dumps(config.get("config_hashes", {}))
                    ))
                    for event in value("events", []) or []:
                        ev = event if isinstance(event, dict) else event.model_dump(mode="json")
                        db.execute("INSERT INTO node_events(run_id,stage,timestamp,details_json) VALUES(?,?,?,?)",
                            (run_id, ev.get("stage",""), str(ev.get("timestamp","")), json.dumps(ev.get("details",{}))))
                    for decision in value("decision_log", []) or []:
                        d = decision if isinstance(decision, dict) else decision.model_dump()
                        db.execute("INSERT INTO decisions(run_id,decision,backend,label,probability,escalated) VALUES(?,?,?,?,?,?)",
                            (run_id,d.get("decision",""),d.get("backend"),d.get("label"),d.get("probability"),int(d.get("escalated",False))))
                    for attempt in value("sql", []) or []:
                        a = attempt if isinstance(attempt, dict) else attempt.model_dump()
                        db.execute("INSERT INTO sql_attempts(run_id,sql_text,validation,error) VALUES(?,?,?,?)",
                            (run_id,a.get("text",""),a.get("validation"),a.get("error")))
                    evidence = value("evidence")
                    if evidence:
                        db.execute("INSERT INTO artifacts(run_id,kind,artifact_id,payload_json) VALUES(?,?,?,?)",
                            (run_id,"evidence",evidence.get("evidence_id","") if isinstance(evidence,dict) else evidence.evidence_id,
                             json.dumps(evidence if isinstance(evidence,dict) else evidence.model_dump(mode="json"))))
                        evidence_data = evidence if isinstance(evidence, dict) else evidence.model_dump(mode="json")
                        db.execute("INSERT OR REPLACE INTO evidence(evidence_id,run_id,dataset_id,dataset_version,payload_json) VALUES(?,?,?,?,?)",
                            (evidence_data.get("evidence_id", ""), run_id, evidence_data.get("dataset_id"),
                             evidence_data.get("dataset_version"), json.dumps(evidence_data)))
        except sqlite3.Error:
            failed = self.path.parent / "failed"
            failed.mkdir(parents=True, exist_ok=True)
            (failed / f"{run_id}.json").write_text(json.dumps({
                "run_id": run_id, "question": value("question"), "outcome": value("outcome"),
                "logging_failed": True
            }, indent=2), encoding="utf-8")
            raise
