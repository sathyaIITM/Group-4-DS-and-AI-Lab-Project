"""Tests for the chart data, evidence store, conversation memory and run log."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from analyst.agents.memory import ConversationMemory
from analyst.agents.runlog import RunLogger
from analyst.agents.state import AnalystState
from analyst.agents.stubs import stub_plan
from analyst.contracts import CheckReport, ColumnSpec, QueryResult
from analyst.tools.charts import select_chart
from analyst.tools.evidence import EvidenceStore, build_evidence, is_current


def _result(rows: list[list[str | int | float | bool | None]]) -> QueryResult:
    return QueryResult(
        sql="SELECT period_label, value FROM obs_rain",
        columns=[
            ColumnSpec(name="period_label", type="VARCHAR"),
            ColumnSpec(name="value", type="DOUBLE"),
        ],
        rows=rows,
        row_count=len(rows),
        truncated=False,
        dataset_versions={"obs_rain": "v1"},
        exec_ms=1,
    )


def test_chart_uses_result_rows() -> None:
    plan = stub_plan("rain").model_copy(update={"operation": "comparison"})
    spec = select_chart(plan, _result([["Jan", 10.0], ["Feb", 12.0]]))
    assert spec.chart_type == "bar"
    assert spec.vega_lite is not None
    assert spec.vega_lite["encoding"]["y"]["field"] == "value"


def test_single_value_has_no_chart_data() -> None:
    spec = select_chart(stub_plan("rain"), _result([["2010", 3778.1]]))
    assert spec.chart_type == "single_value"
    assert spec.vega_lite is None


def test_evidence_store_round_trip(tmp_path: Path) -> None:
    state = AnalystState(
        run_id="r1",
        question="Rain in 2010?",
        plan=stub_plan("rain"),
        result=_result([["2010", 1.0]]),
        checks=CheckReport(outcomes=[], verdict="pass", caveats=[], retry_hint=None),
    )
    catalogue = {"rain": {"title": "Rain", "dataset_version": "v1"}}
    bundle = build_evidence(state, catalogue)
    store = EvidenceStore(tmp_path / "evidence.sqlite")
    assert store.put(bundle) == "ev_r1"
    loaded = store.get("ev_r1")
    assert loaded is not None
    assert loaded.result.rows[0][1] == 1.0
    assert loaded.contract_version == "1.0"
    assert is_current(loaded, {"rain": "v1"})
    assert not is_current(loaded, {"rain": "v2"})


def test_memory_persists_pending_clarification(tmp_path: Path) -> None:
    memory = ConversationMemory(tmp_path / "memory.sqlite")
    memory.save(
        "c1", pending_clarification={"question": "Which state?", "options": ["UP", "Bihar"]}
    )
    assert memory.get("c1")["pending_clarification"]["question"] == "Which state?"


def test_run_logger_writes_run(tmp_path: Path) -> None:
    logger = RunLogger(tmp_path / "runs.sqlite")
    state = AnalystState(
        run_id="r1",
        conversation_id="c1",
        question="test",
        outcome="declined",
        outcome_cause="not_covered",
    )
    logger.write_state(state)
    with sqlite3.connect(tmp_path / "runs.sqlite") as db:
        row = db.execute("SELECT outcome,cause FROM runs WHERE run_id='r1'").fetchone()
    assert row == ("declined", "not_covered")
