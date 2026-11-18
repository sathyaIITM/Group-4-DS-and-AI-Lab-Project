from datetime import date
from decimal import Decimal

import duckdb
import pytest

from analyst.tools.periods import (
    latest_complete_period,
    months_in_window,
    quarter_bounds,
    resolve_period,
    to_agri_year,
    to_fiscal_year,
    to_survey_year,
)
from analyst.tools.units import (
    IncompatibleUnitsError,
    convert_unit,
    display_decimals,
    format_indian,
    parse_numbers,
)


@pytest.mark.parametrize(
    ("factory", "start", "end", "label"),
    [
        (to_survey_year, date(2019, 7, 1), date(2020, 6, 30), "2019-20"),
        (to_fiscal_year, date(2019, 4, 1), date(2020, 3, 31), "2019-20"),
        (to_agri_year, date(2019, 7, 1), date(2020, 6, 30), "2019-20"),
    ],
)
def test_indian_year_windows(factory, start, end, label) -> None:
    window = factory(2019)
    assert (window.start, window.end, window.label) == (start, end, label)


def test_resolve_period_uses_table_convention_and_assumption() -> None:
    catalogue = {
        "tables": [
            {
                "dataset_id": "labour",
                "period_types": ["survey_year"],
                "period_start_month": 7,
            }
        ]
    }
    resolved = resolve_period("2019", "labour", catalogue)
    assert resolved.window is not None
    assert (resolved.window.start, resolved.window.end) == (date(2019, 7, 1), date(2020, 6, 30))
    assert resolved.assumption is not None and resolved.assumption.code == "D7"
    assert resolve_period("2019", "unknown", catalogue).status == "unresolved"


def test_resolve_fiscal_year_and_monsoon() -> None:
    catalogue = {
        "prices": {"period_types": ["fiscal_year"], "period_start_month": 4},
        "rain": {"period_types": ["season"], "period_start_month": None},
    }
    fy = resolve_period("FY23", "prices", catalogue)
    assert fy.window is not None and fy.window.label == "2022-23"
    monsoon = resolve_period("monsoon 2017", "rain", catalogue)
    assert monsoon.window is not None
    assert (monsoon.window.start, monsoon.window.end) == (date(2017, 6, 1), date(2017, 9, 30))


def test_latest_complete_period_reads_max_end_date() -> None:
    db = duckdb.connect()
    db.execute(
        "CREATE TABLE obs_demo (period_type VARCHAR, period_label VARCHAR, "
        "period_start DATE, period_end DATE)"
    )
    db.execute(
        "INSERT INTO obs_demo VALUES "
        "('survey_year','2019-20','2019-07-01','2020-06-30'), "
        "('survey_year','2020-21','2020-07-01','2021-06-30')"
    )
    latest = latest_complete_period("demo", "survey_year", db)
    assert latest.label == "2020-21" and latest.default_applied == "LATEST_PERIOD"
    db.close()


def test_months_and_quarter_bounds_are_inclusive() -> None:
    assert months_in_window(date(2024, 12, 31), date(2025, 2, 1)) == [
        (2024, 12),
        (2025, 1),
        (2025, 2),
    ]
    assert quarter_bounds("2024-Q4") == (date(2024, 10, 1), date(2024, 12, 31))
    assert quarter_bounds("2023-Q4", "fiscal") == (date(2024, 1, 1), date(2024, 3, 31))


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (1, "tonne", "kg", Decimal(1000)),
        (2, "quintal", "tonne", Decimal("0.2")),
        (1, "crore", "lakh", Decimal(100)),
        (1, "crore INR", "INR", Decimal(10_000_000)),
    ],
)
def test_convert_unit(value, source, target, expected) -> None:
    assert convert_unit(value, source, target) == expected


def test_convert_unit_rejects_cross_dimension_and_percent_points() -> None:
    with pytest.raises(IncompatibleUnitsError):
        convert_unit(1, "kg", "INR")
    with pytest.raises(IncompatibleUnitsError):
        convert_unit(25, "percent", "percentage points")


def test_indian_formatting_and_display_precision() -> None:
    assert format_indian(1234567, "persons") == "12.35 lakh"
    assert format_indian(12500000, "INR") == "1.25 crore INR"
    assert format_indian("25.75", "%", 1) == "25.8 percent"
    assert format_indian(1234567, "", 0) == "12,34,567"
    assert display_decimals("percent") == 1
    assert display_decimals("INR") == 2
    assert display_decimals("persons") == 0


def test_parse_numbers_keeps_periods_distinct_from_values() -> None:
    parsed = parse_numbers("It rose to 25.7% in 2019-20, from 1.2 crore.")
    assert [(item.value, item.unit_hint, item.is_period) for item in parsed] == [
        (Decimal("25.7"), "percent", False),
        (Decimal("2019"), None, True),
        (Decimal("1.2"), "crore", False),
    ]
