"""Tests for the read-only SQL runner (src/analyst/tools/sql_runner.py)."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from analyst.tools.sql_runner import ReadOnlyDatabase, SqlRejectedError, SqlTimeoutError, check_sql

TABLES = {"rain", "unemployment"}


@pytest.fixture
def database(tmp_path: Path) -> ReadOnlyDatabase:
    path = tmp_path / "rain.parquet"
    pd.DataFrame({"state": ["Kerala", "Odisha"], "mm": [3000.0, 1500.0]}).to_parquet(path)
    return ReadOnlyDatabase({"rain": path})


def test_select_returns_rows(database: ReadOnlyDatabase) -> None:
    columns, rows = database.run("SELECT state FROM rain WHERE mm > 2000")
    assert columns == ["state"]
    assert rows == [("Kerala",)]


def test_cte_and_union_are_allowed() -> None:
    check_sql("WITH a AS (SELECT 1 AS x) SELECT x FROM a", TABLES)
    check_sql("SELECT 1 UNION ALL SELECT 2", TABLES)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE rain",
        "DELETE FROM rain",
        "INSERT INTO rain VALUES ('x', 1)",
        "UPDATE rain SET mm = 0",
        "CREATE TABLE t AS SELECT 1",
        "SELECT 1; SELECT 2",
        "COPY rain TO '/tmp/out.csv'",
        "ATTACH 'x.db'",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM other_table",
        "not sql at all (",
    ],
)
def test_unsafe_or_unknown_statements_are_rejected(sql: str) -> None:
    with pytest.raises(SqlRejectedError):
        check_sql(sql, TABLES)


def test_external_access_is_disabled(database: ReadOnlyDatabase) -> None:
    with pytest.raises(duckdb.Error):
        database._con.execute("SELECT * FROM read_csv('/etc/hosts')")


def test_long_query_times_out(tmp_path: Path) -> None:
    path = tmp_path / "big.parquet"
    pd.DataFrame({"mm": [float(i) for i in range(5000)]}).to_parquet(path)
    database = ReadOnlyDatabase({"big": path})
    slow = "SELECT sum(a.mm * b.mm * c.mm) FROM big a, big b, big c"
    with pytest.raises(SqlTimeoutError):
        database.run(slow, timeout_s=0.5)


def test_table_functions_are_rejected() -> None:
    with pytest.raises(SqlRejectedError):
        check_sql("SELECT * FROM range(10)", TABLES)
