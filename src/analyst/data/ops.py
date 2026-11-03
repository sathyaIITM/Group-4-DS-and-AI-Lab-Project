"""Generic, reusable preprocessing operations.

Every function here is table-agnostic: behaviour comes from arguments that the
source configuration supplies. Nothing in this module names a dataset.
"""

import calendar
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from analyst.data.config import FlagPattern, PeriodSection, ReadSection, UnitRule
from analyst.data.contract import EMPTY_VALUE_FLAGS, Flag
from analyst.data.source_rules import RULES

REFERENCE_DIR = Path("configs/reference")


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------
def clean_text(value: Any) -> Any:
    """Normalise non-breaking and repeated spaces; empty text becomes NA."""
    if pd.isna(value):
        return pd.NA
    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    return text if text else pd.NA


def clean_header(value: object) -> str:
    """Clean a column header, including XML-escaped spaces such as ``Min_x0020_Price``."""
    return str(clean_text(str(value).replace("_x0020_", " "))).strip()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def slug_with_hash(text: str, prefix: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]  # noqa: S324 - identifier only
    return f"{prefix}_{slug(text)[:90]}_{digest}"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Clean headers and cells. Returns the frame and the number of cells changed."""
    frame = raw.copy()
    frame.columns = [clean_header(column) for column in frame.columns]
    before = frame.astype("string")
    frame = frame.apply(lambda column: column.map(clean_text)).astype("string")
    changed = int((before.fillna("") != frame.fillna("")).to_numpy().sum())
    return frame, changed


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------
def _append(rule: pd.Series, mask: pd.Series, text: str) -> None:
    rule.loc[mask] = rule.loc[mask].map(lambda r: f"{r};{text}".lstrip(";"))


def parse_values(
    raw: pd.Series, read: ReadSection, rule_ids: list[str]
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Parse one column of source text into (value, flag, rule).

    Order: missing-value markers, published flag patterns, registered source rules,
    then the number itself. Text that is none of these is flagged ``unparsed``;
    it is never guessed.
    """
    token = raw.astype("string").fillna("")
    index = token.index
    flag = pd.Series([None] * len(index), index=index, dtype=object)
    rule = pd.Series([""] * len(index), index=index, dtype=object)
    numeric_text = token.copy()

    for marker, marker_flag in read.missing_markers.items():
        hit = pd.Series(token.eq(marker).to_numpy(dtype=bool) & flag.isna().to_numpy(), index=index)
        flag.loc[hit] = marker_flag
        _append(rule, hit, f"marker:{marker or 'empty'}")

    for pattern in read.flag_patterns:
        matched = flag.isna() & token.str.match(pattern.pattern, na=False)
        if pattern.strip:
            numeric_text.loc[matched] = token.loc[matched].str.replace(
                pattern.pattern, r"\1", regex=True
            )
        flag.loc[matched] = pattern.flag
        _append(rule, matched, f"pattern:{pattern.name}")

    for rule_id in rule_ids:
        RULES[rule_id].fn(token, numeric_text, flag, rule)

    cleaned = numeric_text.str.replace(",", "", regex=False)
    for char in read.strip_chars:
        cleaned = cleaned.str.replace(char, "", regex=False)
    cleaned = cleaned.str.strip()
    value = pd.to_numeric(cleaned, errors="coerce").astype("float64")

    carries_no_value = flag.isin(EMPTY_VALUE_FLAGS)
    value = value.mask(carries_no_value)
    failed = value.isna() & ~carries_no_value
    flag.loc[failed] = Flag.UNPARSED.value
    _append(rule, failed, "parse_failed")
    return value, flag, rule


def unit_from_label(label: str, rules: list[UnitRule], default: str) -> str:
    lowered = label.lower()
    for unit_rule in rules:
        if unit_rule.contains.lower() in lowered:
            return unit_rule.unit
    return default


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------
def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def survey_year_bounds(start_year: int, start_month: int) -> tuple[date, date]:
    """First and last day of a year that starts in ``start_month`` of ``start_year``."""
    start = date(start_year, start_month, 1)
    if start_month == 1:
        return start, date(start_year, 12, 31)
    return start, month_end(start_year + 1, start_month - 1)


def year_window(period: PeriodSection, start_year: int) -> tuple[date, date, int]:
    """First day, last day and start month of the year published as ``start_year``.

    A stated exception wins; otherwise the latest convention whose first year is not
    after ``start_year``; otherwise the base ``start_month`` (January when absent).
    """
    for exception in period.exceptions:
        if exception.year == start_year:
            return exception.start_date, exception.end_date, exception.start_date.month
    month = period.start_month or 1
    for convention in period.conventions:
        if convention.from_year <= start_year:
            month = convention.start_month
    first, last = survey_year_bounds(start_year, month)
    return first, last, month


def parse_dates(raw: pd.Series, date_format: str) -> pd.Series:
    """Strict date parsing; text that does not match the format becomes NaT."""
    return pd.to_datetime(raw.astype("string"), format=date_format, errors="coerce")


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------
def load_reference(name: str) -> list[str]:
    frame = pd.read_csv(REFERENCE_DIR / f"{name}.csv", dtype=str)
    return list(frame.iloc[:, 0])


def load_aliases(name: str = "place_aliases", *, missing_ok: bool = False) -> dict[str, str]:
    """Published spelling -> canonical name, from ``configs/reference/<name>.csv``."""
    path = REFERENCE_DIR / f"{name}.csv"
    if missing_ok and not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str)
    return dict(zip(frame["alias"], frame["canonical"], strict=True))


def normalise_name(text: str) -> str:
    """Spelling-insensitive form of a place name: case and spacing are ignored."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip().casefold()


def match_names(
    source: pd.Series, canonical: set[str], aliases: dict[str, str], totals: set[str]
) -> tuple[pd.Series, pd.Series]:
    """Map published names to canonical names. Returns (name, match status).

    Order: the exact canonical name or a total; the alias table; the same name ignoring
    case and spacing (reported as ``alias``, with the published spelling kept in the
    ``*_source`` columns). Nothing else is guessed.
    """
    by_form: dict[str, set[str]] = {}
    for name in canonical:
        by_form.setdefault(normalise_name(name), set()).add(name)
    for alias, target in aliases.items():
        if target in canonical:
            by_form.setdefault(normalise_name(alias), set()).add(target)
    total_forms = {normalise_name(total): total for total in totals}
    names: list[str] = []
    status: list[str] = []
    for text in source.astype("string").fillna(""):
        form = normalise_name(text)
        candidates = by_form.get(form, set())
        if text in totals or text in canonical:
            names.append(text)
            status.append("exact")
        elif aliases.get(text) in canonical:
            names.append(aliases[text])
            status.append("alias")
        elif form in total_forms:
            names.append(total_forms[form])
            status.append("alias")
        elif len(candidates) == 1:
            names.append(next(iter(candidates)))
            status.append("alias")
        else:
            names.append(text)
            status.append("unmatched")
    return pd.Series(names, index=source.index), pd.Series(status, index=source.index)


def flag_patterns_summary(patterns: list[FlagPattern]) -> list[str]:
    return [pattern.name for pattern in patterns]
