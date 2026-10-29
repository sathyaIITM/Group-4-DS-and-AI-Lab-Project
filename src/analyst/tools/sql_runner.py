"""Read-only SQL execution over versioned Parquet with DuckDB.

Every statement is parsed with sqlglot and must be a single SELECT (CTEs and set
operations allowed) that reads only registered tables. Execution is capped by a
timeout. The model never receives a writable connection.
"""

import re
import threading
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp

TIMEOUT_S = 10.0
MAX_ROWS = 1000


class SqlRejectedError(ValueError):
    """The statement is not an allowed read-only query."""


class SqlTimeoutError(TimeoutError):
    """The query exceeded the execution limit."""


def check_sql(sql: str, allowed_tables: set[str]) -> exp.Expression:
    """Parse and validate; return the syntax tree or raise SqlRejectedError."""
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as error:
        msg = f"cannot parse SQL: {error}"
        raise SqlRejectedError(msg) from error
    if len(statements) != 1 or statements[0] is None:
        msg = "exactly one statement is allowed"
        raise SqlRejectedError(msg)
    tree = statements[0]
    if not isinstance(tree, exp.Select | exp.Union | exp.Subquery):
        msg = f"only SELECT queries are allowed, got {type(tree).__name__}"
        raise SqlRejectedError(msg)
    forbidden = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Command,
        exp.Copy,
        exp.Attach,
        exp.Pragma,
        exp.Set,
    )
    if tree.find(*forbidden) is not None:
        msg = "statement contains a data-changing or administrative command"
        raise SqlRejectedError(msg)
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if isinstance(table.this, exp.Func) or name not in allowed_tables | cte_names:
            msg = f"table not in the catalogue: {table.sql()}"
            raise SqlRejectedError(msg)
    return tree


class ReadOnlyDatabase:
    """In-memory DuckDB holding the Parquet tables; the checked SQL cannot write or read files."""

    def __init__(self, tables: dict[str, Path]) -> None:
        self._tables = {name.lower(): path for name, path in tables.items()}
        self._con = duckdb.connect(":memory:")
        for name, path in self._tables.items():
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
                msg = f"invalid table name: {name}"
                raise ValueError(msg)
            literal = str(path).replace("'", "''")
            # Loaded into memory so that file access can be switched off below.
            self._con.execute(
                f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{literal}')"  # noqa: S608
            )
        # Block file and network access from SQL after the views exist.
        self._con.execute("SET enable_external_access = false")
        self._con.execute("SET lock_configuration = true")

    @property
    def table_names(self) -> set[str]:
        return set(self._tables)

    def describe(self, table: str) -> list[tuple[str, str]]:
        """Column names and types of a registered table, for building prompts."""
        if table.lower() not in self._tables:
            msg = f"unknown table: {table}"
            raise SqlRejectedError(msg)
        rows = self._con.execute(f"DESCRIBE {table}").fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def run(
        self, sql: str, timeout_s: float = TIMEOUT_S
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Validate and execute; return column names and at most MAX_ROWS rows."""
        check_sql(sql, self.table_names)
        timer = threading.Timer(timeout_s, self._con.interrupt)
        timer.start()
        try:
            cursor = self._con.execute(sql)
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchmany(MAX_ROWS)
        except duckdb.InterruptException as error:
            msg = f"query exceeded {timeout_s} s"
            raise SqlTimeoutError(msg) from error
        finally:
            timer.cancel()
        return columns, rows
