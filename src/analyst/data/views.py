"""Agent-facing tables, derived from the observation table by configuration.

The observation table is the source of truth. The agent-facing table keeps the shape
the evaluation sets and prompts already use (long for NFHS-5, one row per record for
Mandi, per-year wide for IMD and PLFS), with the contract's quality columns added.
"""

import pandas as pd

from analyst.data.config import SourceConfig, ViewDerived
from analyst.data.contract import FLAG_RANK, Flag

RANK_FLAG = {rank: flag for flag, rank in FLAG_RANK.items()}


def _first_rows(obs: pd.DataFrame) -> pd.DataFrame:
    return obs.drop_duplicates("source_row").set_index("source_row")


def _rowwise(values: pd.Series) -> pd.Series:
    """Collapse per-value text lists (``a;b``) of one source row into a set."""
    return values.dropna().str.split(";").explode().dropna()


def _derived(spec: ViewDerived, obs: pd.DataFrame, index: pd.Index) -> pd.Series:
    if spec.from_ == "constant":
        return pd.Series(spec.value, index=index)
    if spec.from_ == "period_valid":
        valid = obs.groupby("source_row")["period_start"].apply(lambda s: bool(s.notna().all()))
        return valid.reindex(index)
    if spec.from_ in ("check_failed", "check_passed"):
        failed = (
            obs.assign(
                hit=obs["checks_failed"]
                .fillna("")
                .map(lambda text: any(name in text.split(";") for name in spec.checks))
            )
            .groupby("source_row")["hit"]
            .any()
            .reindex(index, fill_value=False)
        )
        return failed if spec.from_ == "check_failed" else ~failed
    hit = (
        obs.assign(hit=obs["quality_flag"].isin(spec.flags))
        .groupby("source_row")["hit"]
        .any()
        .reindex(index, fill_value=False)
    )
    return hit


def _worst_flag(obs: pd.DataFrame, index: pd.Index) -> pd.Series:
    ranks = obs["quality_flag"].map(FLAG_RANK).groupby(obs["source_row"]).min()
    return ranks.map(RANK_FLAG).reindex(index)


def _union_text(obs: pd.DataFrame, column: str, index: pd.Index) -> pd.Series:
    def merge(series: pd.Series) -> str | None:
        parts = sorted({p for text in series.dropna() for p in str(text).split(";")})
        return ";".join(parts) if parts else None

    return obs.groupby("source_row")[column].apply(merge).reindex(index)


def _take(first: pd.DataFrame, source: str) -> pd.Series:
    if ":" in source:
        column, part = source.split(":")
        extracted: pd.Series = getattr(pd.to_datetime(first[column]).dt, part)
        return extracted
    return first[source]


def build_agent_view(config: SourceConfig, obs: pd.DataFrame) -> pd.DataFrame:
    """Derive the agent-facing table for one dataset."""
    view = config.view
    if view.mode == "rows":
        rows = obs.reset_index(drop=True)
        out = pd.DataFrame({name: rows[source] for name, source in view.columns.items()})
        for name, text in view.constants.items():
            out[name] = text
        for spec in view.derived:
            out[spec.name] = _derived_rows(spec, rows)
        out["quality_flag"] = rows["quality_flag"]
        out["rule_ids"] = rows["rule_ids"]
    else:
        first = _first_rows(obs)
        index = first.index
        out = pd.DataFrame({name: _take(first, src) for name, src in view.columns.items()})
        for name, text in view.constants.items():
            out[name] = text
        if view.mode == "pivot_indicator":
            order = list(dict.fromkeys(obs["indicator_id"]))
            wide = obs.pivot(index="source_row", columns="indicator_id", values="value")[order]
        else:
            order = list(dict.fromkeys(obs["period_source"]))
            wide = obs.pivot(index="source_row", columns="period_source", values="value")[order]
            wide.columns = [f"{view.column_prefix}{c}" for c in wide.columns]
        out = out.join(wide.reindex(index))
        for spec in view.derived:
            out[spec.name] = _derived(spec, obs, index)
        out["quality_flag"] = _worst_flag(obs, index)
        out["rule_ids"] = _union_text(obs, "rule_ids", index)
    for name in view.int_columns:
        out[name] = pd.to_numeric(out[name], errors="coerce").astype("Int64")
    for name in view.date_columns:
        out[name] = pd.to_datetime(out[name])
    out = out.sort_values(view.sort, kind="stable") if view.sort else out.sort_index()
    return out.reset_index(drop=True)


def _derived_rows(spec: ViewDerived, rows: pd.DataFrame) -> pd.Series:
    """Row-for-row views: a derived column is a test on that row's own flag."""
    if spec.from_ in ("flag_equals", "flag_in"):
        return rows["quality_flag"].isin(spec.flags)
    if spec.from_ == "constant":
        return pd.Series(spec.value, index=rows.index)
    msg = f"derived column kind {spec.from_!r} is not supported for row-for-row views"
    raise ValueError(msg)


__all__ = ["Flag", "build_agent_view"]
