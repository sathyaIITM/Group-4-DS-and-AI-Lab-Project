"""The pipeline engine: one raw file plus one configuration gives one observation table.

Steps (see docs/specs/data_contract_v1.md): clean, check columns, parse values, run declared
checks, resolve periods and places, reshape to one row per value, validate. Anything
unexpected becomes a review item with a suggested configuration change; the engine
never corrects a value on an assumption.
"""

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analyst.data import ops
from analyst.data.config import Check, SourceConfig
from analyst.data.contract import (
    FLAG_RANK,
    OBS_HEAD,
    OBS_TAIL,
    Flag,
    ReviewItem,
)
from analyst.data.periods import check_periods, unverified_periods
from analyst.data.validate import validate_obs

RANK_FLAG = {rank: flag for flag, rank in FLAG_RANK.items()}
REPORTED_RANK = FLAG_RANK[Flag.REPORTED.value]


@dataclass
class ValueColumn:
    """One source column that holds values, with what it stands for."""

    header: str
    key: str  # indicator id (mode indicators) or period header (mode periods)
    indicator_id: str
    indicator_label: str
    unit: str
    order: int


@dataclass
class RunResult:
    config: SourceConfig
    obs: pd.DataFrame
    review: list[ReviewItem]
    lineage: dict[str, Any]
    columns_seen: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(item.severity == "block" for item in self.review)


# ---------------------------------------------------------------------------
# Reading and column checks
# ---------------------------------------------------------------------------
def _roles(config: SourceConfig) -> dict[str, tuple[str, ...]]:
    return {header: tuple(role.split(":")) for header, role in config.columns.items()}


def _is_period_header(config: SourceConfig, header: str) -> bool:
    pattern = config.values.pattern
    if config.values.mode != "periods" or pattern is None:
        return False
    return re.match(pattern, header) is not None


def check_columns(
    config: SourceConfig, columns: list[str], approved: list[str] | None
) -> list[ReviewItem]:
    """Compare the headers with the configuration and the approved header snapshot."""
    items: list[ReviewItem] = []
    present = set(columns)
    required = set(config.columns) | set(config.values.columns) | set(config.values.period_columns)
    missing_required = sorted(required - present)
    for header in missing_required:
        items.append(
            ReviewItem(
                dataset_id=config.dataset_id,
                severity="block",
                kind="column_missing",
                detail=f"column {header!r} named in the configuration is not in the file",
                count=1,
                suggestion=_rename_hint(header, sorted(present - required)),
            )
        )
    if approved is None:
        items.append(
            ReviewItem(
                dataset_id=config.dataset_id,
                severity="warn",
                kind="no_column_snapshot",
                detail="no approved header snapshot; column drift cannot be checked",
                suggestion="run scripts/run_pipeline.py --approve after review",
            )
        )
        return items
    dropped = sorted(set(approved) - present - set(missing_required))
    added = sorted(present - set(approved))
    new_periods = [header for header in added if _is_period_header(config, header)]
    for header in new_periods:
        items.append(
            ReviewItem(
                dataset_id=config.dataset_id,
                severity="info",
                kind="new_period",
                detail=f"new period column {header!r} matches the period pattern",
                count=1,
            )
        )
    for header in dropped:
        items.append(
            ReviewItem(
                dataset_id=config.dataset_id,
                severity="block",
                kind="column_dropped",
                detail=f"column {header!r} was in the approved file and is gone",
                count=1,
                suggestion=_rename_hint(header, added),
            )
        )
    for header in sorted(set(added) - set(new_periods)):
        items.append(
            ReviewItem(
                dataset_id=config.dataset_id,
                severity="block",
                kind="column_added",
                detail=f"new column {header!r} is not in the approved file",
                count=1,
                suggestion=(
                    "declare it in [columns] or [values], or add it to drop_columns; "
                    "then approve the header snapshot"
                ),
            )
        )
    return items


def _rename_hint(header: str, candidates: list[str]) -> str:
    close = difflib.get_close_matches(header, candidates, n=1, cutoff=0.6)
    if close:
        return f"possible rename of {header!r} to {close[0]!r}: update the configuration"
    return "restore the column, or remove it from the configuration"


# ---------------------------------------------------------------------------
# Value columns
# ---------------------------------------------------------------------------
def value_columns(config: SourceConfig, df: pd.DataFrame) -> list[ValueColumn]:
    values = config.values
    roles = set(config.columns)
    found: list[ValueColumn] = []
    if values.mode == "periods":
        indicator = values.indicator
        if indicator is None:
            msg = "values.indicator is required when the columns are periods"
            raise ValueError(msg)
        for order, header in enumerate(df.columns):
            matches = header in values.period_columns or _is_period_header(config, header)
            if header in roles or not matches:
                continue
            found.append(
                ValueColumn(
                    header=header,
                    key=header,
                    indicator_id=indicator.id,
                    indicator_label=indicator.label or indicator.id,
                    unit=indicator.unit,
                    order=order,
                )
            )
        return found
    for order, header in enumerate(df.columns):
        if header in values.columns:
            spec = values.columns[header]
            found.append(
                ValueColumn(
                    header=header,
                    key=spec.id,
                    indicator_id=spec.id,
                    indicator_label=spec.label or header,
                    unit=spec.unit,
                    order=order,
                )
            )
        elif values.remaining and header not in roles:
            unit = ops.unit_from_label(header, values.unit_rules, values.default_unit)
            indicator_id = (
                ops.slug_with_hash(header, values.id_prefix)
                if values.id_prefix
                else ops.slug(header)
            )
            found.append(
                ValueColumn(
                    header=header,
                    key=indicator_id,
                    indicator_id=indicator_id,
                    indicator_label=header,
                    unit=unit,
                    order=order,
                )
            )
    return found


# ---------------------------------------------------------------------------
# Declared checks on the wide frame (one column per value column)
# ---------------------------------------------------------------------------
def _check_targets(check: Check) -> list[str]:
    """Columns or indicators a check refers to by name (empty when it covers all)."""
    names: list[str | None]
    if check.kind in ("range", "order"):
        names = list(check.indicators)
    elif check.kind == "sum":
        names = [check.total, *check.parts]
    elif check.kind == "ratio":
        names = [check.numerator, check.denominator, check.target]
    elif check.kind == "bound_multiple":
        names = [check.left, check.right]
    else:
        names = []
    return [name for name in names if name]


def _failures(check: Check, wide: pd.DataFrame, units: dict[str, str]) -> pd.DataFrame:
    """Boolean frame, True where the check fails. NaN never fails (already flagged)."""
    fail = pd.DataFrame(False, index=wide.index, columns=wide.columns)
    if check.kind == "range":
        targets = [c for c in (check.indicators or list(wide.columns)) if c in wide.columns]
        for column in targets:
            bounds = check.units.get(units.get(column, ""), [check.min, check.max])
            low, high = bounds
            series = wide[column]
            bad = pd.Series(False, index=wide.index)
            if low is not None:
                bad |= series < low
            if high is not None:
                bad |= series > high
            fail[column] = bad
    elif check.kind == "order":
        cols = check.indicators
        if all(c in wide.columns for c in cols):
            bad = pd.Series(False, index=wide.index)
            for left, right in pairwise(cols):
                bad |= wide[left] > wide[right]
            for column in cols:
                fail[column] = bad
    elif check.kind == "sum":
        cols = [c for c in (check.total, *check.parts) if c is not None]
        if check.total in wide.columns and all(c in wide.columns for c in check.parts):
            expected = wide[check.parts].sum(axis=1, min_count=len(check.parts))
            bad = (expected - wide[check.total]).abs() > check.atol
            bad &= expected.notna() & wide[check.total].notna()
            for column in cols:
                fail[column] = bad
    elif check.kind == "ratio":
        if all(c in wide.columns for c in (check.numerator, check.denominator, check.target)):
            expected = (
                wide[check.numerator] / wide[check.denominator].replace(0, np.nan) * check.scale
            )
            close = np.isclose(wide[check.target], expected, atol=check.atol, rtol=0)
            bad = pd.Series(~close, index=wide.index)
            bad &= expected.notna() & wide[check.target].notna()
            fail[check.target] = bad
    elif check.kind == "bound_multiple":
        if check.left in wide.columns and check.right in wide.columns:
            bad = wide[check.left] > check.factor * wide[check.right]
            fail[check.left] = bad
            fail[check.right] = bad
    return fail


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------
def _year_label(year: int, start_month: int | None) -> str:
    if start_month in (None, 1):
        return str(year)
    return f"{year}-{(year + 1) % 100:02d}"


def _row_periods(df: pd.DataFrame, config: SourceConfig) -> pd.DataFrame:
    """Period of each row when columns are indicators."""
    period = config.period
    roles = _roles(config)
    index = df.index
    if period.type == "survey_round":
        if not (period.start and period.end and period.label):
            msg = "period.type = survey_round needs period.label, period.start and period.end"
            raise ValueError(msg)
        return pd.DataFrame(
            {
                "period_type": "survey_round",
                "period_label": period.label,
                "period_source": period.label,
                "period_start": pd.Timestamp(period.start),
                "period_end": pd.Timestamp(period.end),
            },
            index=index,
        )
    if period.type == "quarter":
        return _quarter_periods(df, config)
    header = next(h for h, role in roles.items() if role[0] in ("period_year", "period_date"))
    source = df[header]
    if period.type == "date":
        if not period.date_format:
            msg = "period.type = date needs period.date_format"
            raise ValueError(msg)
        parsed = ops.parse_dates(source, period.date_format)
        return pd.DataFrame(
            {
                "period_type": "date",
                "period_label": parsed.dt.strftime("%Y-%m-%d"),
                "period_source": source,
                "period_start": parsed,
                "period_end": parsed,
            },
            index=index,
        )
    years = pd.to_numeric(source.str.replace(",", "", regex=False), errors="coerce")
    starts: list[Any] = []
    ends: list[Any] = []
    labels: list[Any] = []
    for year in years:
        if pd.isna(year):
            starts.append(pd.NaT)
            ends.append(pd.NaT)
            labels.append(None)
            continue
        first, last, month = ops.year_window(period, int(year))
        starts.append(pd.Timestamp(first))
        ends.append(pd.Timestamp(last))
        labels.append(_year_label(int(year), month))
    return pd.DataFrame(
        {
            "period_type": period.type,
            "period_label": labels,
            "period_source": source,
            "period_start": pd.to_datetime(pd.Series(starts, index=index)),
            "period_end": pd.to_datetime(pd.Series(ends, index=index)),
        },
        index=index,
    )


def _quarter_periods(df: pd.DataFrame, config: SourceConfig) -> pd.DataFrame:
    """Period of each row from a year column and a quarter-name column."""
    period = config.period
    roles = _roles(config)
    year_header = next((h for h, r in roles.items() if r[0] == "period_year"), None)
    quarter_header = next((h for h, r in roles.items() if r[0] == "period_quarter"), None)
    if year_header is None or quarter_header is None:
        msg = "period.type = quarter needs columns with the roles period_year and period_quarter"
        raise ValueError(msg)
    specs = {ops.normalise_name(name): spec for name, spec in period.quarter_map.items()}
    years = pd.to_numeric(df[year_header].str.replace(",", "", regex=False), errors="coerce")
    starts: list[Any] = []
    ends: list[Any] = []
    labels: list[str | None] = []
    for year, text in zip(years, df[quarter_header].astype("string").fillna(""), strict=True):
        spec = specs.get(ops.normalise_name(str(text)))
        if pd.isna(year) or spec is None:
            starts.append(pd.NaT)
            ends.append(pd.NaT)
            labels.append(None)
            continue
        first_year = int(year) + spec.year_offset
        last_year = first_year + (1 if spec.end_month < spec.start_month else 0)
        starts.append(pd.Timestamp(date(first_year, spec.start_month, 1)))
        ends.append(pd.Timestamp(ops.month_end(last_year, spec.end_month)))
        labels.append(f"{int(year)}-{spec.label}")
    return pd.DataFrame(
        {
            "period_type": "quarter",
            "period_label": labels,
            "period_source": df[year_header].astype("string") + " " + df[quarter_header],
            "period_start": pd.to_datetime(pd.Series(starts, index=df.index)),
            "period_end": pd.to_datetime(pd.Series(ends, index=df.index)),
        },
        index=df.index,
    )


def _column_period(config: SourceConfig, header: str, df: pd.DataFrame) -> pd.DataFrame:
    """Period of each row for one value column when columns are periods."""
    index = df.index
    values = config.values
    if header in values.period_columns:
        spec = values.period_columns[header]
        year_header = next(h for h, role in _roles(config).items() if role[0] == "period_year")
        years = pd.to_numeric(df[year_header], errors="coerce")
        starts: list[Any] = []
        ends: list[Any] = []
        labels: list[str | None] = []
        for year in years:
            if pd.isna(year):
                starts.append(pd.NaT)
                ends.append(pd.NaT)
                labels.append(None)
                continue
            year_int = int(year)
            starts.append(pd.Timestamp(date(year_int, spec.start_month, 1)))
            ends.append(pd.Timestamp(ops.month_end(year_int, spec.end_month)))
            if spec.type == "month":
                labels.append(f"{year_int}-{spec.start_month:02d}")
            elif spec.type == "season":
                labels.append(f"{year_int}-{header.upper()}")
            else:
                labels.append(str(year_int))
        return pd.DataFrame(
            {
                "period_type": spec.type,
                "period_label": labels,
                "period_source": header,
                "period_start": pd.to_datetime(pd.Series(starts, index=index)),
                "period_end": pd.to_datetime(pd.Series(ends, index=index)),
            },
            index=index,
        )
    match = re.match(values.pattern or "", header)
    if match is None:
        msg = f"column {header!r} is not in values.period_columns and does not match values.pattern"
        raise ValueError(msg)
    start_year = int(match.group(1))
    suffix = match.group(2) if match.re.groups >= 2 else None
    first, last, month = ops.year_window(config.period, start_year)
    return pd.DataFrame(
        {
            "period_type": config.period.type,
            "period_label": f"{start_year}-{suffix}" if suffix else _year_label(start_year, month),
            "period_source": header,
            "period_start": pd.Timestamp(first),
            "period_end": pd.Timestamp(last),
        },
        index=index,
    )


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------
def _places(df: pd.DataFrame, config: SourceConfig) -> pd.DataFrame:
    roles = _roles(config)
    geo = config.geo
    index = df.index

    def column_of(role: str) -> pd.Series | None:
        header = next((h for h, r in roles.items() if r[0] == role), None)
        return df[header] if header else None

    state_src = column_of("geo_state")
    district_src = column_of("geo_district")
    market_src = column_of("geo_market")
    subdiv_src = column_of("geo_subdivision")
    aliases = ops.load_aliases()
    totals = set(geo.total_members)
    empty = pd.Series([None] * len(index), index=index, dtype=object)

    out = pd.DataFrame(index=index)
    out["geo_state_source"] = state_src if state_src is not None else empty
    out["geo_district_source"] = district_src if district_src is not None else empty
    match = pd.Series(["exact"] * len(index), index=index, dtype=object)
    state_name = empty.copy()
    if state_src is not None and geo.state_reference:
        canonical = set(ops.load_reference(geo.state_reference))
        names, status = ops.match_names(state_src, canonical, aliases, totals)
        state_name, match = names.astype(object), status.astype(object)
    elif state_src is not None:
        state_name = state_src.astype(object)
    is_total = state_name.isin(totals) if state_src is not None else pd.Series(False, index=index)

    subdiv_name = empty.copy()
    if subdiv_src is not None:
        canonical = set(ops.load_reference(geo.subdivision_reference or "imd_subdivisions"))
        sub_aliases = (
            ops.load_aliases(geo.subdivision_alias_reference, missing_ok=True)
            if geo.subdivision_alias_reference
            else {}
        )
        names, match = ops.match_names(subdiv_src, canonical, sub_aliases, set())
        subdiv_name, match = names.astype(object), match.astype(object)

    level = pd.Series([geo.level] * len(index), index=index, dtype=object)
    level[is_total] = "national"
    by_level = {"market": market_src, "district": district_src, "subdivision": subdiv_src}
    national = pd.Series([geo.national_name] * len(index), index=index, dtype=object)
    chosen = national if geo.level == "national" else by_level.get(geo.level, state_src)
    if chosen is None:
        msg = f"geo.level = {geo.level} needs a column with the matching geo role in [columns]"
        raise ValueError(msg)
    name_source: pd.Series = chosen
    out["geo_name_source"] = name_source
    names_final = name_source.astype(object).copy()
    if geo.level == "state":
        names_final = state_name.copy()
    elif geo.level == "subdivision":
        names_final = subdiv_name.copy()
    names_final[is_total] = geo.national_name
    out["geo_name"] = names_final
    out["geo_state"] = state_name.where(~is_total, None)
    out["geo_district"] = district_src if district_src is not None else empty
    out["geo_level"] = level
    out["geo_match"] = match
    out["is_total_row"] = is_total.astype(bool)
    out["geo_vintage"] = geo.vintage

    codes = []
    for lvl, st, di, mk, nm in zip(
        out["geo_level"],
        out["geo_state"],
        out["geo_district"],
        market_src if market_src is not None else empty,
        out["geo_name"],
        strict=True,
    ):
        if lvl == "national":
            codes.append("IN")
        elif lvl == "state":
            codes.append(f"state:{ops.slug(str(nm))}")
        elif lvl == "district":
            codes.append(f"district:{ops.slug(str(st))}/{ops.slug(str(di))}")
        elif lvl == "market":
            codes.append(f"market:{ops.slug(str(st))}/{ops.slug(str(di))}/{ops.slug(str(mk))}")
        else:
            codes.append(f"{lvl}:{ops.slug(str(nm))}")
    out["geo_code"] = codes
    return out


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def run_source(
    config: SourceConfig,
    raw_dir: Path,
    *,
    raw_frame: pd.DataFrame | None = None,
    approved_columns: list[str] | None = None,
) -> RunResult:
    """Run one source through the pipeline. ``raw_frame`` replaces the file (for tests)."""
    dataset = config.dataset
    review: list[ReviewItem] = []
    raw_path = raw_dir / dataset.raw_file
    if raw_frame is None:
        raw = pd.read_csv(raw_path, dtype="string", keep_default_na=False)
        raw_sha = ops.sha256_of(raw_path)
    else:
        raw = raw_frame.astype("string")
        raw_sha = "in-memory"

    def blocked_result(item: ReviewItem) -> RunResult:
        return RunResult(config, pd.DataFrame(), [*review, item], {"dataset_id": dataset.id})

    if config.period.type == "survey_year" and config.period.start_month is None:
        return blocked_result(
            ReviewItem(
                dataset_id=dataset.id,
                severity="block",
                kind="period_convention_unknown",
                detail="period.type is survey_year but period.start_month is not stated",
                suggestion="state the month the year starts in (a label such as 2017-18 does not)",
            )
        )

    frame, cells_changed = ops.clean_frame(raw)
    columns_seen = list(frame.columns)
    review += check_columns(config, columns_seen, approved_columns)
    frame = frame.drop(columns=[c for c in config.read.drop_columns if c in frame.columns])
    if any(item.kind == "column_missing" for item in review):
        return RunResult(config, pd.DataFrame(), review, {"dataset_id": dataset.id}, columns_seen)

    rows_in = len(frame)
    if config.read.dedupe_exact:
        frame = frame.drop_duplicates()
        if rows_in - len(frame):
            review.append(
                ReviewItem(
                    dataset_id=dataset.id,
                    severity="info",
                    kind="duplicates_removed",
                    detail="exact duplicate rows removed",
                    count=rows_in - len(frame),
                )
            )
    duplicates_dropped = rows_in - len(frame)

    vcols = value_columns(config, frame)
    rule_ids = [rule.id for rule in config.rules]
    values: dict[str, pd.Series] = {}
    flags: dict[str, pd.Series] = {}
    rules: dict[str, pd.Series] = {}
    for vcol in vcols:
        values[vcol.key], flags[vcol.key], rules[vcol.key] = ops.parse_values(
            frame[vcol.header], config.read, rule_ids
        )
    wide = pd.DataFrame(values)
    base_rank = pd.DataFrame(
        {key: flags[key].map(lambda f: FLAG_RANK[f] if f else REPORTED_RANK) for key in flags}
    ).astype(int)
    rule_wide = pd.DataFrame(rules)
    checks_wide = pd.DataFrame("", index=wide.index, columns=wide.columns, dtype=object)
    units = {vcol.key: vcol.unit for vcol in vcols}

    for check in config.checks:
        if check.kind == "unique_key":
            continue
        absent = [name for name in _check_targets(check) if name not in wide.columns]
        if absent:
            review.append(
                ReviewItem(
                    dataset_id=dataset.id,
                    severity="warn",
                    kind="check_target_missing",
                    detail=f"check {check.name!r} names {absent}, which are not in the table; "
                    "it does not run",
                    count=len(absent),
                    suggestion="correct the names in [[checks]] or remove the check",
                )
            )
        fail = _failures(check, wide, units)
        rank = FLAG_RANK[check.flag]
        failed = fail.to_numpy()
        base_rank = pd.DataFrame(
            np.where(failed, np.minimum(base_rank.to_numpy(), rank), base_rank.to_numpy()),
            index=base_rank.index,
            columns=base_rank.columns,
        )
        checks_wide = checks_wide.where(~fail, checks_wide + ";" + check.name)
        rule_wide = rule_wide.where(~fail, rule_wide + ";check:" + check.name)

    places = _places(frame, config)
    row_period = _row_periods(frame, config) if config.values.mode == "indicators" else None
    attr_roles = {h: r for h, r in _roles(config).items() if r[0] in ("category", "attr")}

    pieces: list[pd.DataFrame] = []
    for vcol in vcols:
        piece = pd.DataFrame(index=frame.index)
        piece["dataset_id"] = dataset.id
        piece["dataset_version"] = f"{dataset.config_version}+{raw_sha[:8]}"
        piece["source_row"] = frame.index.to_numpy(dtype="int64")
        for column in places.columns:
            piece[column] = places[column]
        period = (
            row_period if row_period is not None else _column_period(config, vcol.header, frame)
        )
        for column in period.columns:
            piece[column] = period[column]
        piece["indicator_id"] = vcol.indicator_id
        piece["indicator_label_source"] = vcol.indicator_label
        for header, role in attr_roles.items():
            name = role[1]
            series = frame[header]
            if len(role) > 2 and role[2] == "int":
                series = pd.to_numeric(series.str.replace(",", "", regex=False), errors="coerce")
                series = series.astype("Int64")
            piece[name] = series
        piece["value"] = wide[vcol.key]
        piece["unit"] = vcol.unit
        piece["value_raw"] = frame[vcol.header]
        piece["quality_flag"] = base_rank[vcol.key].map(RANK_FLAG)
        piece["rule_ids"] = rule_wide[vcol.key]
        piece["checks_failed"] = checks_wide[vcol.key]
        piece["_order"] = vcol.order
        pieces.append(piece)
    obs = pd.concat(pieces, ignore_index=True)

    # A row whose period could not be parsed cannot be placed in time: flag every value.
    bad_period = obs["period_start"].isna()
    obs.loc[bad_period, "quality_flag"] = Flag.UNPARSED.value
    obs.loc[bad_period, "rule_ids"] = obs.loc[bad_period, "rule_ids"].map(
        lambda r: f"{r};period_unparsed".lstrip(";")
    )

    for check in config.checks:
        if check.kind != "unique_key":
            continue
        duplicated = obs.duplicated(subset=check.columns, keep=False)
        obs.loc[duplicated, "quality_flag"] = Flag.INCONSISTENT.value
        obs.loc[duplicated, "checks_failed"] = (
            obs.loc[duplicated, "checks_failed"] + f";{check.name}"
        )
        obs.loc[duplicated, "rule_ids"] = obs.loc[duplicated, "rule_ids"] + f";check:{check.name}"
        if duplicated.any():
            review.append(
                ReviewItem(
                    dataset_id=dataset.id,
                    severity="block",
                    kind="duplicate_key",
                    detail=f"{int(duplicated.sum())} values share the key {check.columns}",
                    count=int(duplicated.sum()),
                    suggestion="check the source for repeated rows; deduplicate only if exact",
                )
            )

    for column in ("rule_ids", "checks_failed"):
        obs[column] = obs[column].map(
            lambda text: None if text is None or not str(text).strip(";") else str(text).strip(";")
        )
    obs = obs.sort_values(["source_row", "_order"], kind="stable").drop(columns="_order")
    extra = [c for c in obs.columns if c not in OBS_HEAD and c not in OBS_TAIL]
    obs = obs[[*OBS_HEAD, *extra, *OBS_TAIL]].reset_index(drop=True)
    obs["period_start"] = pd.to_datetime(obs["period_start"])
    obs["period_end"] = pd.to_datetime(obs["period_end"])

    review += _review_from_flags(config, obs)
    review += validate_obs(config, obs)
    review += check_periods(config, obs)
    review += unverified_periods(config, obs)

    rule_counts: Counter[str] = Counter()
    for text in obs["rule_ids"].dropna():
        rule_counts.update(text.split(";"))
    lineage = {
        "dataset_id": dataset.id,
        "dataset_version": obs["dataset_version"].iloc[0] if len(obs) else None,
        "config_version": dataset.config_version,
        "raw_file": dataset.raw_file,
        "raw_sha256": raw_sha,
        "rows_in": len(raw),
        "rows_after_dedupe": int(rows_in - duplicates_dropped),
        "observations": len(obs),
        "cells_text_cleaned": cells_changed,
        "values_touched_by_rule": dict(sorted(rule_counts.items())),
        "flag_counts": obs["quality_flag"].value_counts().sort_index().to_dict(),
        "source_rules": {rule_id: _rule_note(rule_id) for rule_id in rule_ids},
    }
    return RunResult(config, obs, review, lineage, columns_seen)


def _rule_note(rule_id: str) -> dict[str, Any]:
    from analyst.data.source_rules import RULES

    rule = RULES[rule_id]
    return {"description": rule.description, "evidence": rule.evidence}


def _review_from_flags(config: SourceConfig, obs: pd.DataFrame) -> list[ReviewItem]:
    """Aggregate value-level problems into review items, with examples."""
    dataset_id = config.dataset_id
    items: list[ReviewItem] = []

    unmatched = obs.loc[obs["geo_match"] == "unmatched", "geo_name_source"].dropna()
    if len(unmatched):
        names = sorted(set(unmatched))
        subdivision_level = config.geo.level == "subdivision"
        canonical = ops.load_reference(
            (config.geo.subdivision_reference or "imd_subdivisions")
            if subdivision_level
            else (config.geo.state_reference or "states")
        )
        alias_file = (
            f"{config.geo.subdivision_alias_reference or 'subdivision_aliases'}.csv"
            if subdivision_level
            else "place_aliases.csv"
        )
        forms = {ops.normalise_name(c): c for c in canonical}
        hints = {
            n: [
                forms[f]
                for f in difflib.get_close_matches(ops.normalise_name(n), list(forms), 1, 0.6)
            ]
            for n in names[:5]
        }
        items.append(
            ReviewItem(
                dataset_id=dataset_id,
                severity="block",
                kind="geo_unmatched",
                detail=f"{len(names)} place names match no reference or alias: {names[:5]}",
                count=len(unmatched),
                suggestion=(
                    f"add rows to configs/reference/{alias_file} "
                    + "; ".join(f"{n} -> {h[0]}?" for n, h in hints.items() if h)
                ),
            )
        )

    flagged = obs[obs["quality_flag"] != Flag.REPORTED.value]
    for flag, group in flagged.groupby("quality_flag"):
        if flag == Flag.UNPARSED.value:
            period_bad = group["period_start"].isna()
            tokens = sorted(set(group.loc[~period_bad, "value_raw"].dropna()))[:5]
            if (~period_bad).any():
                items.append(
                    ReviewItem(
                        dataset_id=dataset_id,
                        severity="block",
                        kind="unparsed_token",
                        detail=f"text that is not a number or a known marker, e.g. {tokens}",
                        count=int((~period_bad).sum()),
                        suggestion=(
                            f"add {tokens[:1]} to read.missing_markers with its flag, "
                            "or register a source rule"
                        ),
                    )
                )
            if period_bad.any():
                examples = sorted(set(group.loc[period_bad, "period_source"].dropna()))[:5]
                items.append(
                    ReviewItem(
                        dataset_id=dataset_id,
                        severity="block",
                        kind="unparsed_period",
                        detail=f"periods that do not match the configured format, e.g. {examples}",
                        count=int(period_bad.sum()),
                        suggestion=(
                            "update period.date_format, values.pattern or period.quarter_map, "
                            "or fix the source"
                        ),
                    )
                )
        elif flag in (Flag.OUT_OF_RANGE.value, Flag.INCONSISTENT.value, Flag.IMPLAUSIBLE.value):
            if (group["checks_failed"].fillna("").str.contains("unique")).all():
                continue
            checks = Counter(";".join(group["checks_failed"].dropna()).split(";"))
            checks.pop("", None)
            items.append(
                ReviewItem(
                    dataset_id=dataset_id,
                    severity="warn",
                    kind=str(flag),
                    detail=f"values failing declared checks {dict(checks)}; kept and flagged",
                    count=len(group),
                    suggestion="confirm the source value; widen the check bounds if it is right",
                )
            )
        else:
            items.append(
                ReviewItem(
                    dataset_id=dataset_id,
                    severity="info",
                    kind=str(flag),
                    detail="expected flag from a configured marker or pattern",
                    count=len(group),
                )
            )
    return items
