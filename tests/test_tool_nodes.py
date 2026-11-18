from __future__ import annotations

from pathlib import Path

import pandas as pd

from analyst.agents.state import AnalystState
from analyst.agents.stubs import stub_plan
from analyst.agents.tool_nodes import ToolNodeDependencies, make_tool_nodes
from analyst.contracts import SqlAttempt
from analyst.tools.sql_runner import ReadOnlyDatabase


def test_tool_nodes_validate_and_execute_read_only_sql(tmp_path: Path) -> None:
    parquet = tmp_path / "obs_demo.parquet"
    pd.DataFrame({"dataset_version": ["v1"], "value": [12.5]}).to_parquet(parquet)
    deps = ToolNodeDependencies(
        catalogue={"demo": {"dataset_id": "demo", "period_types": []}},
        refs={},
        database_for=lambda _dataset: ReadOnlyDatabase({"obs_demo": parquet}),
    )
    nodes = make_tool_nodes(deps)
    attempt = SqlAttempt(
        attempt=1,
        kind="generate",
        sql="SELECT value FROM obs_demo",
        statement="read the value",
        valid=False,
        error_class="parse",
        error="not yet checked",
        executed_ms=None,
    )
    state = AnalystState(plan=stub_plan("demo"), sql=[attempt])
    validation = nodes["validate_sql_with_sqlglot"](state)
    assert validation["validation_result"] == "valid"

    state = state.model_copy(update={"validation_result": "valid"})
    execution = nodes["execute_read_only_duckdb"](state)
    assert execution["execution_result"] == "success"
    assert execution["result"]["rows"] == [[12.5]]
    assert execution["result"]["dataset_versions"] == {"demo": "stub"}
