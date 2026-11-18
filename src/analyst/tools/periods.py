"""Calendar and table-aware period resolution for Indian public statistics."""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from pydantic import Field

from analyst.contracts import Assumption, Contract, PeriodWindow


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
        type=kind,  # type: ignore[arg-type]
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
        type=period_type,  # type: ignore[arg-type]
        label=str(label),
        start=start.date() if hasattr(start, "date") else start,
        end=end.date() if hasattr(end, "date") else end,
        default_applied="LATEST_PERIOD",
    )


def _catalogue_entry(dataset_id: str, catalogue: Any) -> Mapping[str, Any] | None:
    if isinstance(catalogue, Mapping):
        if dataset_id in catalogue and isinstance(catalogue[dataset_id], Mapping):
            return catalogue[dataset_id]
        tables = catalogue.get("tables", [])
    else:
        tables = getattr(catalogue, "tables", [])
    for table in tables:
        row = table if isinstance(table, Mapping) else getattr(table, "model_dump", lambda: {})()
        if row.get("dataset_id") == dataset_id:
            return row
    return None


def resolve_period(mention: str, dataset_id: str, catalogue: Any) -> PeriodResolution:
    """Resolve a year, fiscal year, month, or monsoon period using published conventions."""
    entry = _catalogue_entry(dataset_id, catalogue)
    if entry is None:
        return PeriodResolution(status="unresolved", options=[])
    types = set(entry.get("period_types", []))
    start_month = entry.get("period_start_month")
    text = mention.strip()
    lower = text.casefold()
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

    season_match = re.fullmatch(r"(?i)(?:monsoon|jjas)\s+(\d{4})", text)
    if season_match and "season" in types:
        year = int(season_match.group(1))
        window = PeriodWindow(
            requested=text,
            type="season",
            label=f"JJAS {year}",
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
            month = {"survey_year": 7, "fiscal_year": 4, "agri_year": 7}[kind]
            return PeriodResolution(status="resolved", window=_window(kind, year, month, text))
        return PeriodResolution(status="unresolved", options=sorted(types))
    if year_match:
        year = int(year_match.group(1))
        kind = _year_type(types, start_month)
        if kind == "calendar_year":
            return PeriodResolution(status="resolved", window=_window(kind, year, 1, text))
        if kind in {"survey_year", "agri_year"}:
            return PeriodResolution(
                status="resolved",
                window=_window(kind, year, 7, text),
                assumption=Assumption(
                    code="D7",
                    text="Bare year interpreted as the July-June year starting in that year.",
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
