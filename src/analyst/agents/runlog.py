"""The run log (design document Section 9): one record set per run, written once.

SQLite at `RUN_LOG_DB` (default `outputs/runs/runs.sqlite`). The record of a run is written in a
single transaction by `finalize_response`. Child tables use the primary key `(run_id, seq)`.
A logging failure never blocks the answer: the state is written to
`outputs/runs/failed/<run_id>.json` instead. Neither keys nor addresses nor account data are
stored.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analyst.agents.state import AnalystState
from analyst.contracts import CONTRACT_VERSION
from analyst.inference.llm import LlmCallRecord

SCHEMA_VERSION = 1
DEFAULT_PATH = "outputs/runs/runs.sqlite"
SUMMARY_LIMIT = 2048

DDL = """
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, turn INTEGER, question TEXT NOT NULL,
 question_id TEXT, eval_set TEXT, experiment TEXT, member TEXT, machine_id TEXT,
 started_at TEXT NOT NULL, ended_at TEXT NOT NULL, duration_ms INTEGER, first_event_ms INTEGER,
 version TEXT NOT NULL, config_hash TEXT, git_sha TEXT, git_dirty INTEGER,
 contract_version TEXT, catalogue_hash TEXT, outcome TEXT, cause TEXT, badge TEXT,
 final_text TEXT, evidence_id TEXT, llm_calls INTEGER, tokens_in INTEGER, tokens_out INTEGER,
 cost_usd_est REAL, deadline_hit INTEGER, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS node_events (
 run_id TEXT NOT NULL, seq INTEGER NOT NULL, node TEXT, started_ms INTEGER, duration_ms INTEGER,
 status TEXT, summary TEXT, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS llm_calls (
 run_id TEXT NOT NULL, seq INTEGER NOT NULL, node TEXT, purpose TEXT, provider TEXT, model TEXT,
 model_version TEXT, prompt_id TEXT, prompt_version INTEGER, prompt_sha256 TEXT,
 temperature REAL, variables TEXT, rendered_prompt TEXT, response_text TEXT, parsed_ok INTEGER,
 parse_error TEXT, tokens_in INTEGER, tokens_out INTEGER, latency_ms INTEGER,
 cost_usd_est REAL, retry_of_seq INTEGER, thinking_level TEXT, reasoning_tokens INTEGER,
 finish_reason TEXT, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS decisions (
 run_id TEXT NOT NULL, seq INTEGER NOT NULL, decision TEXT, backend TEXT, model_revision TEXT,
 state_text TEXT, label TEXT, probabilities TEXT, calibrated INTEGER, temperature REAL,
 escalated INTEGER, fallback INTEGER, latency_ms INTEGER, cost_usd_est REAL,
 PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS retrievals (
 run_id TEXT NOT NULL, seq INTEGER NOT NULL, stage TEXT, query TEXT, domain_boost INTEGER,
 widened INTEGER, backend TEXT, hits TEXT, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS sql_attempts (
 run_id TEXT NOT NULL, seq INTEGER NOT NULL, attempt INTEGER, kind TEXT, sql TEXT,
 statement TEXT, valid INTEGER, error_class TEXT, error TEXT, row_count INTEGER, exec_ms INTEGER,
 dataset_versions TEXT, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS checks (
 run_id TEXT NOT NULL, seq INTEGER NOT NULL, name TEXT, passed INTEGER, failure_class TEXT,
 expected TEXT, observed TEXT, detail TEXT, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS artifacts (
 run_id TEXT PRIMARY KEY, intent TEXT, plan TEXT, coverage TEXT, narrations TEXT,
 number_check TEXT, chart TEXT, retry_hints TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
 evidence_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, bundle TEXT NOT NULL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS data_requests (
 run_id TEXT NOT NULL, question TEXT, missing TEXT, pointers TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
 run_id TEXT NOT NULL, rating TEXT, note TEXT, by TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS memory (
 conversation_id TEXT PRIMARY KEY, turn INTEGER, pending_clarification TEXT,
 prior_result_ref TEXT, prior_plan TEXT, prior_sql TEXT, updated_at TEXT
);
"""


def _json(value: Any) -> str | None:
    """Serialise a value or model to JSON text, or return None."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, list):
        value = [v.model_dump(mode="json") if hasattr(v, "model_dump") else v for v in value]
    return json.dumps(value, default=str, ensure_ascii=False)


def _git(*args: str) -> str | None:
    """Run a fixed git command and return its output, or None if git is unavailable."""
    try:
        out = subprocess.check_output(  # noqa: S603  # fixed git arguments
            ["git", *args],  # noqa: S607
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def code_version() -> tuple[str, int]:
    """The commit of the running code and whether the working tree has changes."""
    sha = _git("rev-parse", "HEAD") or "unknown"
    return sha, int(bool(_git("status", "--porcelain")))


def catalogue_hash(path: Path = Path("data/processed/catalogue.json")) -> str | None:
    """Return the SHA-256 of the published catalogue, or None if it is absent."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def llm_rows(records: list[LlmCallRecord]) -> list[dict[str, Any]]:
    """Flatten call records, earlier attempts first, assigning `seq` and `retry_of_seq`."""
    rows: list[dict[str, Any]] = []

    def add(record: LlmCallRecord, retry_of_seq: int | None) -> int:
        """Add one model-call row and return its sequence number."""
        seq = len(rows) + 1
        row = record.model_dump(exclude={"earlier_attempts", "retry_of"}, mode="json")
        row["variables"] = json.dumps(row["variables"], default=str)
        row["seq"], row["retry_of_seq"] = seq, retry_of_seq
        rows.append(row)
        return seq

    # A successful call carries its failed attempts in `earlier_attempts`; a call that failed
    # every attempt arrives as sibling records (from `LlmError.records`), each with `retry_of`
    # set to the index of the previous sibling. Both forms map to the seq of the retried row.
    siblings: list[int] = []
    for record in records:
        seqs = [add(a, None) for a in record.earlier_attempts]
        if record.retry_of is None:
            siblings = []
            retry = seqs[-1] if seqs else None
        elif record.earlier_attempts:
            retry = seqs[record.retry_of] if record.retry_of < len(seqs) else seqs[-1]
        else:
            retry = siblings[record.retry_of] if record.retry_of < len(siblings) else None
        siblings.append(add(record, retry))
    return rows


class RunLogger:
    """Buffered per-run SQLite writer; a run is committed in one transaction."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("RUN_LOG_DB", DEFAULT_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._set_aside_old_schema()
        with sqlite3.connect(self.path) as db:
            db.executescript(DDL)

    def _set_aside_old_schema(self) -> None:
        """A database from before schema_version 1 cannot be migrated; keep it under a new name."""
        if not self.path.exists():
            return
        with sqlite3.connect(self.path) as db:
            columns = [r[1] for r in db.execute("PRAGMA table_info(runs)")]
        if columns and "schema_version" not in columns:
            self.path.rename(self.path.with_suffix(".pre_schema_v1.sqlite"))

    def write_state(self, state: AnalystState) -> None:
        """Write the record set of a finished run. Never raises; a failure leaves a JSON file."""
        try:
            self._write(state)
        except Exception as error:  # the answer is returned whatever happens to the log
            failed = self.path.parent / "failed"
            failed.mkdir(parents=True, exist_ok=True)
            record = {
                "error": f"{type(error).__name__}: {error}",
                "state": state.model_dump(mode="json"),
            }
            (failed / f"{state.run_id or 'unknown'}.json").write_text(
                json.dumps(record, default=str, indent=2), encoding="utf-8"
            )

    def _write(self, state: AnalystState) -> None:
        """Write all records of one run to the run log."""
        run_id = state.run_id
        ended = datetime.now(UTC)
        started = (
            state.started_at if state.started_at.tzinfo else state.started_at.replace(tzinfo=UTC)
        )
        duration_ms = int((ended - started).total_seconds() * 1000)
        events = state.events
        offsets = [int((e.at - started).total_seconds() * 1000) for e in events]
        llm = llm_rows(state.llm_records)
        sha, dirty = code_version()
        meta = state.meta
        evidence = state.evidence
        deadline_hit = int(state.outcome_cause == "deadline_exceeded")
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            db.execute(
                "INSERT INTO runs VALUES (" + ",".join("?" * 30) + ")",  # noqa: S608
                (
                    run_id,
                    state.conversation_id,
                    int(meta.get("turn") or 1),
                    state.question,
                    meta.get("question_id"),
                    meta.get("eval_set") or "adhoc",
                    meta.get("experiment"),
                    meta.get("member"),
                    hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12],
                    started.isoformat(),
                    ended.isoformat(),
                    duration_ms,
                    offsets[0] if offsets else None,
                    state.config.version,
                    hashlib.sha256(state.config.model_dump_json().encode()).hexdigest(),
                    sha,
                    dirty,
                    CONTRACT_VERSION,
                    catalogue_hash(),
                    state.outcome,
                    state.outcome_cause,
                    state.confidence.badge if state.confidence else None,
                    state.response_text,
                    evidence.evidence_id if evidence else None,
                    len(llm),
                    sum(record["tokens_in"] for record in llm),
                    sum(record["tokens_out"] for record in llm),
                    sum(record["cost_usd_est"] or 0.0 for record in llm),
                    deadline_hit,
                    SCHEMA_VERSION,
                ),
            )
            seen: set[str] = set()
            for i, event in enumerate(events):
                nxt = offsets[i + 1] if i + 1 < len(events) else offsets[i]
                status = "retry" if event.stage in seen else "ok"
                seen.add(event.stage or "")
                summary = json.dumps(event.payload, default=str)[:SUMMARY_LIMIT]
                db.execute(
                    "INSERT INTO node_events VALUES (?,?,?,?,?,?,?)",
                    (run_id, event.seq, event.stage, offsets[i], nxt - offsets[i], status, summary),
                )
            for row in llm:
                db.execute(
                    "INSERT INTO llm_calls VALUES (" + ",".join("?" * 24) + ")",  # noqa: S608
                    (
                        run_id,
                        row["seq"],
                        row["node"],
                        row["purpose"],
                        row["provider"],
                        row["model"],
                        row["model_version"],
                        row["prompt_id"],
                        row["prompt_version"],
                        row["prompt_sha256"],
                        row["temperature"],
                        row["variables"],
                        row["rendered_prompt"],
                        row["response_text"],
                        int(row["parsed_ok"]),
                        row["parse_error"],
                        row["tokens_in"],
                        row["tokens_out"],
                        row["latency_ms"],
                        row["cost_usd_est"],
                        row["retry_of_seq"],
                        row["thinking_level"],
                        row["reasoning_tokens"],
                        row["finish_reason"],
                    ),
                )
            for seq, decision in enumerate(state.decision_log, 1):
                db.execute(
                    "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        seq,
                        decision.decision,
                        decision.backend,
                        decision.model_revision,
                        None,
                        decision.label,
                        json.dumps(decision.probabilities),
                        int(decision.calibrated),
                        decision.temperature,
                        int(decision.escalated),
                        int(decision.fallback),
                        decision.latency_ms,
                        decision.cost_usd,
                    ),
                )
            for seq, retrieval in enumerate(self._retrievals(state), 1):
                db.execute(
                    "INSERT INTO retrievals VALUES (?,?,?,?,?,?,?,?)", (run_id, seq, *retrieval)
                )
            for seq, attempt in enumerate(state.sql, 1):
                last = seq == len(state.sql) and state.result is not None
                db.execute(
                    "INSERT INTO sql_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        seq,
                        attempt.attempt,
                        attempt.kind,
                        attempt.sql,
                        attempt.statement,
                        int(attempt.valid),
                        attempt.error_class,
                        attempt.error,
                        state.result.row_count if last and state.result else None,
                        attempt.executed_ms,
                        _json(state.result.dataset_versions) if last and state.result else None,
                    ),
                )
            outcomes = state.checks.outcomes if state.checks else []
            for seq, check in enumerate(outcomes, 1):
                db.execute(
                    "INSERT INTO checks VALUES (?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        seq,
                        check.name,
                        int(check.passed),
                        check.failure_class,
                        check.expected,
                        check.observed,
                        check.detail,
                    ),
                )
            db.execute(
                "INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    _json(state.intent),
                    _json(state.plan),
                    _json(state.coverage),
                    _json(state.narration),
                    _json(state.number_check),
                    _json(state.chart),
                    _json(state.retry_hints),
                ),
            )
            if evidence:
                db.execute(
                    "INSERT OR REPLACE INTO evidence VALUES (?,?,?,?)",
                    (
                        evidence.evidence_id,
                        run_id,
                        evidence.model_dump_json(),
                        evidence.created_at.isoformat(),
                    ),
                )
            if state.outcome == "declined":
                cov = state.coverage
                db.execute(
                    "INSERT INTO data_requests VALUES (?,?,?,?,?)",
                    (
                        run_id,
                        state.question,
                        _json(cov.missing if cov else []),
                        _json(cov.pointers if cov else []),
                        ended.isoformat(),
                    ),
                )

    @staticmethod
    def _retrievals(state: AnalystState) -> list[tuple[Any, ...]]:
        """Return the retrieval rows of a run: catalogue candidates, cards and examples."""
        rows: list[tuple[Any, ...]] = []
        if state.catalogue_candidates:
            hits = [
                {"id": c["dataset_id"], "kind": "table", "score": c.get("score"), "rank": i}
                for i, c in enumerate(state.catalogue_candidates, 1)
            ]
            rows.append(
                ("catalogue_candidates", state.question, 0, 0, "bm25_only", json.dumps(hits))
            )
        if state.retrieved:
            retrieved = state.retrieved
            hits = [
                {"id": t.get("dataset_id"), "kind": "table", "score": None, "rank": i}
                for i, t in enumerate(retrieved.get("tables", []), 1)
            ]
            hits += [
                {"id": i, "kind": "card", "score": None, "rank": 0}
                for i in retrieved.get("card_ids", [])
            ]
            hits += [
                {"id": i, "kind": "example", "score": None, "rank": 0}
                for i in retrieved.get("example_ids", [])
            ]
            widened = int(state.counters.widened_searches > 0)
            rows.append(
                (
                    "context",
                    state.question,
                    int(bool(retrieved.get("domain_ranked"))),
                    widened,
                    "bm25_only",
                    json.dumps(hits),
                )
            )
        return rows
