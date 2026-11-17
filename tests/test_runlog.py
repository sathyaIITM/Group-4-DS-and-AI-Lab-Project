"""The run log follows design document Section 9 (schema_version 1)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from analyst.agents.graph import invoke_graph
from analyst.agents.runlog import SCHEMA_VERSION, RunLogger, llm_rows
from analyst.agents.state import AnalystState, RunConfig
from analyst.inference.llm import LlmCallRecord

LLM_CALLS_COLUMNS = {
    "run_id",
    "seq",
    "node",
    "purpose",
    "provider",
    "model",
    "model_version",
    "prompt_id",
    "prompt_version",
    "prompt_sha256",
    "temperature",
    "variables",
    "rendered_prompt",
    "response_text",
    "parsed_ok",
    "parse_error",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "cost_usd_est",
    "retry_of_seq",
    # additions recorded by the LLM layer (thinking control)
    "thinking_level",
    "reasoning_tokens",
    "finish_reason",
}
RUNS_COLUMNS = {
    "run_id",
    "conversation_id",
    "turn",
    "question",
    "question_id",
    "eval_set",
    "experiment",
    "member",
    "machine_id",
    "started_at",
    "ended_at",
    "duration_ms",
    "first_event_ms",
    "version",
    "config_hash",
    "git_sha",
    "git_dirty",
    "contract_version",
    "catalogue_hash",
    "outcome",
    "cause",
    "badge",
    "final_text",
    "evidence_id",
    "llm_calls",
    "tokens_in",
    "tokens_out",
    "cost_usd_est",
    "deadline_hit",
    "schema_version",
}


def record(**overrides: object) -> LlmCallRecord:
    fields: dict[str, object] = {
        "node": "extract_query_intent",
        "purpose": "intent",
        "provider": "test",
        "model": "m",
        "model_version": "1",
        "prompt_id": "intent",
        "prompt_version": 1,
        "prompt_sha256": "x",
        "temperature": 0.0,
        "variables": {"q": "a"},
        "rendered_prompt": "p",
        "response_text": "{}",
        "parsed_ok": True,
        "parse_error": None,
        "tokens_in": 10,
        "tokens_out": 5,
        "latency_ms": 3,
        "cost_usd_est": 0.001,
        "thinking_level": "low",
        "reasoning_tokens": 4,
        "finish_reason": "stop",
    }
    return LlmCallRecord(**{**fields, **overrides})


def columns(path: Path, table: str) -> set[str]:
    with sqlite3.connect(path) as db:
        return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def test_tables_have_the_section_9_columns(tmp_path: Path) -> None:
    RunLogger(tmp_path / "runs.sqlite")
    assert columns(tmp_path / "runs.sqlite", "llm_calls") == LLM_CALLS_COLUMNS
    assert columns(tmp_path / "runs.sqlite", "runs") == RUNS_COLUMNS
    with sqlite3.connect(tmp_path / "runs.sqlite") as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names >= {
        "runs",
        "node_events",
        "llm_calls",
        "decisions",
        "retrievals",
        "sql_attempts",
        "checks",
        "artifacts",
        "evidence",
        "data_requests",
        "feedback",
        "memory",
    }


def test_child_rows_are_keyed_by_run_and_seq(tmp_path: Path) -> None:
    RunLogger(tmp_path / "runs.sqlite")
    with sqlite3.connect(tmp_path / "runs.sqlite") as db:
        db.execute("INSERT INTO node_events(run_id, seq) VALUES ('r', 1)")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO node_events(run_id, seq) VALUES ('r', 1)")


@pytest.mark.usefixtures("agent_cwd")
def test_a_run_is_written_once() -> None:
    state = invoke_graph(AnalystState(run_id="r1", question="Rainfall in Kerala in 2010?"))
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        assert db.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM node_events").fetchone()[0] == len(state.events)
        assert db.execute("SELECT schema_version, outcome FROM runs").fetchone() == (
            SCHEMA_VERSION,
            "answered",
        )
        stages = [r[0] for r in db.execute("SELECT node FROM node_events ORDER BY seq")]
    assert stages[0] == "receive_request" and stages[-1] == "finalize_response"


@pytest.mark.usefixtures("agent_cwd")
def test_llm_records_reach_the_table_with_thinking_columns() -> None:
    state = AnalystState(run_id="r2", question="q", llm_records=[record()], config=RunConfig())
    RunLogger().write_state(state)
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        row = db.execute(
            "SELECT thinking_level, reasoning_tokens, finish_reason, tokens_in, retry_of_seq "
            "FROM llm_calls"
        ).fetchone()
        totals = db.execute("SELECT llm_calls, tokens_in, tokens_out FROM runs").fetchone()
    assert row == ("low", 4, "stop", 10, None)
    assert totals == (1, 10, 5)


def test_earlier_attempts_are_flattened_and_linked() -> None:
    first = record(parsed_ok=False, parse_error="bad json")
    second = record(earlier_attempts=[first], retry_of=0)
    rows = llm_rows([second])
    assert [r["seq"] for r in rows] == [1, 2]
    assert [r["retry_of_seq"] for r in rows] == [None, 1]
    assert rows[0]["parsed_ok"] is False


@pytest.mark.usefixtures("agent_cwd")
def test_logging_failure_leaves_a_json_record_and_does_not_raise(tmp_path: Path) -> None:
    logger = RunLogger()
    state = AnalystState(run_id="r3", question="q", llm_records=[record()])
    with sqlite3.connect(logger.path) as db:
        db.execute("DROP TABLE llm_calls")
    logger.write_state(state)
    failed = json.loads(Path("outputs/runs/failed/r3.json").read_text())
    assert "llm_calls" in failed["error"]


@pytest.mark.usefixtures("agent_cwd")
def test_a_database_from_before_schema_v1_is_set_aside() -> None:
    path = Path("outputs/runs/runs.sqlite")
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, finished_at TEXT)")
    RunLogger()
    assert "schema_version" in columns(path, "runs")
    assert path.with_suffix(".pre_schema_v1.sqlite").exists()


@pytest.mark.usefixtures("agent_cwd")
def test_decline_is_logged_as_a_data_request() -> None:
    config = RunConfig(stub_script={"check_coverage": ["not_covered"]}, version="v0")
    invoke_graph(AnalystState(run_id="r4", question="q", config=config))
    with sqlite3.connect("outputs/runs/runs.sqlite") as db:
        row = db.execute("SELECT question, missing FROM data_requests").fetchone()
    assert row[0] == "q" and "stub" in row[1]
