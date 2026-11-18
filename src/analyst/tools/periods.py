"""Calendar and table-aware period resolution for Indian public statistics."""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal, cast

from pydantic import Field

from analyst.contracts import Assumption, Contract, PeriodWindow
from analyst.contracts.common import PeriodType


class PeriodResolution(Contract):
    """A resolved period window or explicit unresolved result with valid options."""

    status: Literal["resolved", "unresolved"]
    window: PeriodWindow | None = None
    assumption: Assumption | None = None
    options: list[str] = Field(default_factory=list)


def _window(kind: str, start_year: int, start_month: int, requested: str) -> PeriodWindow:
    end_year = start_year + (start_month != 1)
    end_month = 12 if start_month == 1 else start_month - 1
    end_day = calendar.monthrange(end_year, end_month)[1]
    if kind == "calendar_year":
        label = str(start_year)
    else:
        label = f"{start_year}-{(start_year + 1) % 100:02d}"
    return PeriodWindow(
        requested=requested,
        type=cast(PeriodType, kind),
        label=label,
        start=date(start_year, start_month, 1),
        end=date(end_year, end_month, end_day),
    )


def to_survey_year(year: int) -> PeriodWindow:
    """Return the July-to-June survey year beginning in ``year``."""
    return _window("survey_year", year, 7, str(year))


def to_fiscal_year(year: int) -> PeriodWindow:
    """Return the April-to-March fiscal year beginning in ``year``."""
    return _window("fiscal_year", year, 4, f"FY{year % 100:02d}")


def to_agri_year(year: int) -> PeriodWindow:
    """Return the July-to-June agricultural year beginning in ``year``."""
    return _window("agri_year", year, 7, str(year))


def latest_complete_period(dataset_id: str, period_type: str, db: Any) -> PeriodWindow:
    """Read the period with the greatest end date from a published observation table."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", dataset_id):
        raise ValueError("dataset_id must be a lowercase identifier")
    table = f"obs_{dataset_id}"
    query = (
        f"SELECT period_label, period_start, period_end FROM {table} "  # noqa: S608 - identifier validated above
        "WHERE period_type = ? AND period_start IS NOT NULL AND period_end IS NOT NULL "
        "ORDER BY period_end DESC LIMIT 1"
    )
    row = db.execute(
        query,
        [period_type],
    ).fetchone()
    if row is None:
        raise LookupError(f"no {period_type} periods found for {dataset_id}")
    label, start, end = row
    return PeriodWindow(
        requested="latest",
        type=cast(PeriodType, period_type),
        label=str(label),
        start=start.date() if hasattr(start, "date") else start,
        end=end.date() if hasattr(end, "date") else end,
        default_applied="LATEST_PERIOD",
    )


def _catalogue_entry(dataset_id: str, catalogue: Any) -> Mapping[str, Any] | None:
    if isinstance(catalogue, Mapping):
        if dataset_id in catalogue and isinstance(catalogue[dataset_id], Mapping):
            return cast(Mapping[str, Any], catalogue[dataset_id])
        tables = catalogue.get("tables", [])
    else:
        tables = getattr(catalogue, "tables", [])
    for table in tables:
        row = table if isinstance(table, Mapping) else getattr(table, "model_dump", lambda: {})()
        if row.get("dataset_id") == dataset_id:
            return row
    return None


def _year_span(text: str) -> tuple[int, int] | None:
    """Read "2019-21", "2019-2021" or "2019\u201321" as (2019, 2021); None for anything else."""
    match = re.fullmatch(r"(\d{4})\s*[-/\u2013]\s*(\d{2}|\d{4})", text.strip())
    if match is None:
        return None
    first, second = int(match.group(1)), int(match.group(2))
    if second < 100:
        second += first - first % 100 + (100 if second < first % 100 else 0)
    return (first, second) if second > first else None


def _survey_round(
    text: str, available_labels: Sequence[str] | None, entry: Mapping[str, Any]
) -> PeriodResolution:
    """Match a survey round by its year span against the labels published in the table."""
    labels = list(available_labels or [])
    span = _year_span(text)
    matches = [label for label in labels if span is not None and _year_span(label) == span]
    matches += [label for label in labels if label.casefold() == text.casefold()]
    matches = list(dict.fromkeys(matches))
    if len(matches) != 1:
        return PeriodResolution(status="unresolved", options=labels[:6])
    label = matches[0]
    first, last = _year_span(label) or (None, None)
    start = entry.get("coverage_start") if len(labels) == 1 else None
    end = entry.get("coverage_end") if len(labels) == 1 else None
    window = PeriodWindow(
        requested=text,
        type="survey_round",
        label=label,
        start=date.fromisoformat(str(start)) if start else date(first or 1900, 1, 1),
        end=date.fromisoformat(str(end)) if end else date(last or 1900, 12, 31),
    )
    return PeriodResolution(status="resolved", window=window)


def resolve_period(
    mention: str,
    dataset_id: str,
    catalogue: Any,
    available_labels: Sequence[str] | None = None,
) -> PeriodResolution:
    """Resolve a year, fiscal year, month, monsoon or survey-round period using published
    conventions. ``available_labels`` are the table's survey-round labels, read by the caller.
    """
    entry = _catalogue_entry(dataset_id, catalogue)
    if entry is None:
        return PeriodResolution(status="unresolved", options=[])
    types = set(entry.get("period_types", []))
    start_month = entry.get("period_start_month")
    text = mention.strip()
    lower = text.casefold()
    if types == {"survey_round"}:
        return _survey_round(text, available_labels, entry)
    if lower in {"latest", "last year"}:
        # Latest requires querying the data; catalogue metadata alone cannot prove completeness.
        labels = entry.get("latest_periods", {})
        candidate = (
            next((labels[kind] for kind in sorted(types) if kind in labels), None)
            if isinstance(labels, Mapping)
            else None
        )
        if candidate is not None:
            return PeriodResolution(
                status="resolved",
                window=PeriodWindow.model_validate(candidate),
                assumption=Assumption(
                    code="LATEST_PERIOD",
                    text=f"Used the latest complete period: {candidate['label']}",
                ),
            )
        return PeriodResolution(status="unresolved", options=sorted(types))

    season_match = re.fullmatch(
        r"(?i)(?:(?:the\s+)?(?:monsoon|jjas)(?:\s+season)?(?:\s+of)?\s+(\d{4})"
        r"|(\d{4})\s+(?:monsoon|jjas)(?:\s+season)?)",
        text,
    )
    if season_match and "season" in types:
        year = int(season_match.group(1) or season_match.group(2))
        window = PeriodWindow(
            requested=text,
            type="season",
            label=f"{year}-JJAS",  # the label published by the IMD table
            start=date(year, 6, 1),
            end=date(year, 9, 30),
        )
        return PeriodResolution(
            status="resolved",
            window=window,
            assumption=Assumption(code="D5", text="Monsoon interpreted as June-September (JJAS)."),
        )

    month_match = re.fullmatch(r"(?i)([A-Za-z]+)\s+(\d{4})", text)
    if month_match and "month" in types:
        month_token = month_match.group(1).casefold()
        month = next(
            (
                index
                for index in range(1, 13)
                if month_token
                in {
                    calendar.month_name[index].casefold(),
                    calendar.month_abbr[index].casefold(),
                }
            ),
            None,
        )
        if month is None:
            return PeriodResolution(status="unresolved", options=[])
        year = int(month_match.group(2))
        window = PeriodWindow(
            requested=text,
            type="month",
            label=f"{year}-{month:02d}",
            start=date(year, month, 1),
            end=date(year, month, calendar.monthrange(year, month)[1]),
        )
        return PeriodResolution(status="resolved", window=window)

    range_match = re.fullmatch(r"(\d{4})\s*[-/\u2013]\s*(\d{2}|\d{4})", text)
    fiscal_match = re.fullmatch(r"(?i)FY\s*(\d{2}|\d{4})", text)
    if fiscal_match and "fiscal_year" in types:
        ending_year = int(fiscal_match.group(1))
        ending_year += (2000 if ending_year < 50 else 1900) if ending_year < 100 else 0
        window = _window("fiscal_year", ending_year - 1, 4, text)
        return PeriodResolution(status="resolved", window=window)
    year_match = re.fullmatch(r"(\d{4})", text)
    if range_match:
        year = int(range_match.group(1))
        suffix = int(range_match.group(2))
        expected = (year + 1) % 100 if suffix < 100 else year + 1
        if suffix != expected:
            return PeriodResolution(status="unresolved", options=sorted(types))
        kind = _year_type(types, start_month)
        if kind in {"survey_year", "fiscal_year", "agri_year"}:
            month = _start_month(kind, start_month)
            return PeriodResolution(status="resolved", window=_window(kind, year, month, text))
        return PeriodResolution(status="unresolved", options=sorted(types))
    if year_match:
        year = int(year_match.group(1))
        kind = _year_type(types, start_month)
        finer = next((grain for grain in ("month", "date") if grain in types), None)
        if kind is None and finer is not None:
            # A year on a monthly or daily table is the span of its months (or days).
            return PeriodResolution(
                status="resolved",
                window=PeriodWindow(
                    requested=text,
                    type=cast(PeriodType, finer),
                    label=str(year),
                    start=date(year, 1, 1),
                    end=date(year, 12, 31),
                ),
                assumption=Assumption(
                    code="YEAR_SPAN", text=f"{year} read as January to December {year}."
                ),
            )
        if kind == "calendar_year":
            return PeriodResolution(status="resolved", window=_window(kind, year, 1, text))
        if kind in {"survey_year", "agri_year"}:
            month = _start_month(kind, start_month)
            window = _window(kind, year, month, text)
            span = "July-June" if month == 7 else "April-March"
            return PeriodResolution(
                status="resolved",
                window=window,
                assumption=Assumption(
                    code="D7",
                    text=f"{year} read as the {span} year {window.label}, which starts in {year}.",
                ),
            )
        if kind == "fiscal_year":
            return PeriodResolution(
                status="resolved",
                window=_window(kind, year, 4, text),
                assumption=Assumption(
                    code="D7",
                    text="Bare year interpreted as the fiscal year starting in that year.",
                ),
            )
    return PeriodResolution(status="unresolved", options=sorted(types))


def _start_month(kind: str, start_month: int | None) -> int:
    """The table's own year start (GSDP is an April-March year labelled ``survey_year``)."""
    if start_month in {4, 7}:
        return int(start_month)
    return {"survey_year": 7, "fiscal_year": 4, "agri_year": 7}[kind]


def _year_type(types: set[str], start_month: int | None) -> str | None:
    if start_month == 1 and "calendar_year" in types:
        return "calendar_year"
    if start_month == 4 and "fiscal_year" in types:
        return "fiscal_year"
    if start_month == 7:
        for kind in ("survey_year", "agri_year"):
            if kind in types:
                return kind
    for kind in ("calendar_year", "survey_year", "fiscal_year", "agri_year"):
        if kind in types:
            return kind
    return None


def months_in_window(start: date, end: date) -> list[tuple[int, int]]:
    """Return inclusive (year, month) pairs intersecting a date window."""
    if end < start:
        raise ValueError("end must not precede start")
    year, month = start.year, start.month
    out = []
    while (year, month) <= (end.year, end.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def quarter_bounds(
    label: str, year_type: Literal["calendar", "fiscal"] = "calendar"
) -> tuple[date, date]:
    """Return inclusive dates for ``YYYY-Qn`` (calendar or April-start fiscal quarters)."""
    match = re.fullmatch(r"(\d{4})\s*[- ]?Q([1-4])", label.strip(), re.IGNORECASE)
    if match is None:
        raise ValueError("quarter label must look like 2024-Q1")
    year, quarter = int(match.group(1)), int(match.group(2))
    first_month = (quarter - 1) * 3 + 1 + (3 if year_type == "fiscal" else 0)
    if first_month > 12:
        year += 1
        first_month -= 12
    last_month = first_month + 2
    end_year = year + (last_month > 12)
    last_month = ((last_month - 1) % 12) + 1
    last_day = calendar.monthrange(end_year, last_month)[1]
    return date(year, first_month, 1), date(end_year, last_month, last_day)
