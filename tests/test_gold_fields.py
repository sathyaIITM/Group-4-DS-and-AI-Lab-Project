"""Tests for the structured gold fields and `scripts/fill_gold_fields.py`."""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from analyst.evaluation.gold_fields import compute_fields, lineage_queries, merge_fields
from analyst.tools.sql_runner import ReadOnlyDatabase


@pytest.fixture
def database(tmp_path: Path) -> ReadOnlyDatabase:
    """A one-table database shaped like an `obs_<dataset>` table."""
    rows = [
        ("Kerala", "state", False, datetime(2019, 7, 1), datetime(2020, 6, 30), 10.0),
        ("Goa", "state", False, datetime(2019, 7, 1), datetime(2020, 6, 30), 13.0),
        ("Bihar", "state", False, datetime(2019, 7, 1), datetime(2020, 6, 30), None),
        ("India", "national", True, datetime(2019, 7, 1), datetime(2020, 6, 30), 4.8),
        ("Kerala", "state", False, datetime(2020, 7, 1), datetime(2021, 6, 30), 10.1),
    ]
    frame = pd.DataFrame(
        rows,
        columns=["geo_name", "geo_level", "is_total_row", "period_start", "period_end", "value"],
    )
    frame["indicator_id"] = "ur"
    frame["unit"] = "percent"
    path = tmp_path / "obs_plfs.parquet"
    frame.to_parquet(path)
    db = ReadOnlyDatabase({"obs_plfs": path})
    yield db
    db.close()


def _item(sql: str | None, action: str = "answer") -> dict:
    return {"id": "e2e-900", "expected_action": action, "gold_sql": sql}


def test_plain_query_keeps_order_and_limit(database: ReadOnlyDatabase) -> None:
    sql = (
        "SELECT geo_name AS entity, value FROM obs_plfs WHERE NOT is_total_row "
        "AND period_start = DATE '2019-07-01' AND value IS NOT NULL ORDER BY value DESC LIMIT 1"
    )
    result = compute_fields(_item(sql), database)
    assert result.mode == "rows"
    assert result.fields["expected_places"] == [{"name": "Goa", "level": "state"}]
    assert result.fields["expected_periods"] == [{"start": "2019-07-01", "end": "2020-06-30"}]
    assert result.fields["indicator_ids"] == ["ur"]
    assert result.fields["unit"] == "percent"
    assert result.fields["n_values"] == 1
    assert result.fields["gold_lineage"] == "rows"


def test_series_counts_values_and_periods(database: ReadOnlyDatabase) -> None:
    sql = "SELECT period_start, value FROM obs_plfs WHERE geo_name = 'Kerala' ORDER BY period_start"
    result = compute_fields(_item(sql), database)
    assert result.fields["n_values"] == 2
    assert len(result.fields["expected_periods"]) == 2
    assert result.fields["expected_places"] == [{"name": "Kerala", "level": "state"}]


def test_null_values_are_not_counted(database: ReadOnlyDatabase) -> None:
    sql = "SELECT geo_name AS entity, value FROM obs_plfs WHERE geo_name = 'Bihar'"
    result = compute_fields(_item(sql), database)
    assert result.fields["n_values"] == 0
    assert result.fields["expected_places"] == [{"name": "Bihar", "level": "state"}]


def test_aggregate_is_traced_through_its_inputs(database: ReadOnlyDatabase) -> None:
    sql = (
        "SELECT AVG(value) AS value FROM obs_plfs WHERE NOT is_total_row "
        "AND period_start = DATE '2019-07-01'"
    )
    queries, mode = lineage_queries(sql)
    assert mode == "inputs"
    assert len(queries) == 1
    result = compute_fields(_item(sql), database)
    names = {p["name"] for p in result.fields["expected_places"]}
    assert names == {"Kerala", "Goa", "Bihar"}
    assert result.fields["n_values"] == 1
    assert result.fields["gold_lineage"] == "inputs"


def test_union_traces_each_branch(database: ReadOnlyDatabase) -> None:
    sql = (
        "SELECT value FROM obs_plfs WHERE geo_name = 'Goa' "
        "UNION ALL SELECT value FROM obs_plfs WHERE geo_name = 'India'"
    )
    result = compute_fields(_item(sql), database)
    assert result.mode == "rows"
    assert [p["name"] for p in result.fields["expected_places"]] == ["Goa", "India"]


def test_join_is_unsupported() -> None:
    queries, mode = lineage_queries("SELECT a.value FROM obs_plfs a JOIN obs_plfs b ON 1 = 1")
    assert (queries, mode) == ([], "unsupported")


def test_non_answer_items_get_empty_fields(database: ReadOnlyDatabase) -> None:
    result = compute_fields(_item(None, action="clarify"), database)
    assert result.mode == "no_sql"
    assert result.fields["expected_places"] == []
    assert result.fields["n_values"] == 0
    assert result.fields["gold_lineage"] is None


def test_merge_adds_placeholders_and_never_overwrites_by_default(
    database: ReadOnlyDatabase,
) -> None:
    sql = "SELECT value FROM obs_plfs WHERE geo_name = 'Goa'"
    computed = compute_fields(_item(sql), database)
    item = {**_item(sql), "domain": "labour", "n_values": 7}
    merged, differences = merge_fields(item, computed)
    assert merged["domain"] == "labour"
    assert merged["clarify_slot"] is None
    assert merged["clarify_options"] is None
    assert merged["n_values"] == 7
    assert differences == ["e2e-900: n_values is 7, computed 1"]
    overwritten, _ = merge_fields(item, computed, overwrite=True)
    assert overwritten["n_values"] == 1


def test_script_dry_run_does_not_write(tmp_path: Path, database: ReadOnlyDatabase) -> None:
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("fill", root / "scripts" / "fill_gold_fields.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    items = [_item("SELECT value FROM obs_plfs WHERE geo_name = 'Goa'"), _item("SELECT nope")]
    filled, report = module.fill(items, database, overwrite=False)
    assert filled[0]["n_values"] == 1
    assert report[1]["mode"] == "error"
    assert json.dumps(filled[0])  # serialisable
