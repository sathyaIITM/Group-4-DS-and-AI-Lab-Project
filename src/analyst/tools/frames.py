"""Safe deterministic transformations for small query result frames."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd

MAX_FRAME_ROWS = 1_000


def _frame(rows: pd.DataFrame | Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if len(frame) > MAX_FRAME_ROWS:
        raise ValueError(f"frame exceeds {MAX_FRAME_ROWS} rows")
    return frame


def filter_rows(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    predicate: Callable[[pd.DataFrame], Any] | None = None,
    **equals: Any,
) -> pd.DataFrame:
    """Filter by an optional vector predicate and exact column values."""
    frame = _frame(rows)
    mask = pd.Series(True, index=frame.index)
    if predicate is not None:
        result = predicate(frame)
        if not isinstance(result, pd.Series) or len(result) != len(frame):
            raise ValueError("predicate must return a same-length pandas Series")
        mask &= result.fillna(False).astype(bool)
    for column, value in equals.items():
        if column not in frame:
            raise KeyError(column)
        mask &= frame[column].eq(value)
    return frame.loc[mask].reset_index(drop=True)


def sort_rows(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    by: str | Sequence[str],
    *,
    ascending: bool | Sequence[bool] = True,
) -> pd.DataFrame:
    frame = _frame(rows)
    columns = [by] if isinstance(by, str) else list(by)
    missing = set(columns) - set(frame.columns)
    if missing:
        raise KeyError(f"unknown sort columns: {sorted(missing)}")
    return frame.sort_values(
        columns, ascending=ascending, kind="mergesort", na_position="last"
    ).reset_index(drop=True)


def top_k(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]], k: int, by: str, *, largest: bool = True
) -> pd.DataFrame:
    if k < 0:
        raise ValueError("k must be non-negative")
    return sort_rows(rows, by, ascending=not largest).head(k).reset_index(drop=True)


def pivot(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    index: str,
    columns: str,
    values: str,
    aggregate: str = "sum",
) -> pd.DataFrame:
    frame = _frame(rows)
    required = {index, columns, values}
    if missing := required - set(frame.columns):
        raise KeyError(f"unknown pivot columns: {sorted(missing)}")
    if aggregate not in {"sum", "mean", "min", "max", "count"}:
        raise ValueError("aggregate must be sum, mean, min, max, or count")
    return pd.pivot_table(
        frame,
        index=index,
        columns=columns,
        values=values,
        aggfunc=aggregate,
        fill_value=0,
        observed=False,
    ).reset_index()


def join_denominator(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    population_table: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    on: str | Sequence[str],
    population_column: str = "population",
) -> pd.DataFrame:
    frame, population = _frame(rows), _frame(population_table)
    keys = [on] if isinstance(on, str) else list(on)
    if population_column not in population:
        raise KeyError(population_column)
    if population.duplicated(keys).any():
        raise ValueError("population table must have one row per join key")
    return frame.merge(
        population[[*keys, population_column]], on=keys, how="left", validate="many_to_one"
    )


def cap_rows(
    rows: pd.DataFrame | Sequence[Mapping[str, Any]], limit: int = MAX_FRAME_ROWS
) -> pd.DataFrame:
    if limit < 0 or limit > MAX_FRAME_ROWS:
        raise ValueError(f"limit must be between 0 and {MAX_FRAME_ROWS}")
    return _frame(rows).head(limit).reset_index(drop=True)
