"""Source configuration: everything table-specific lives in one TOML file per table.

A configuration answers, in fixed sections, what the table is (``dataset``), how the
file is read (``read``), what rows and columns mean (``columns``, ``values``), what
kind of year and place it uses (``period``, ``geo``), which checks must hold
(``checks``) and how the agent-facing table is derived (``view``). Table-specific
code is not allowed here; the only escape hatch is a named rule in the registry of
``source_rules``.
"""

import tomllib
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SOURCES_DIR = Path("configs/sources")


class DatasetSection(BaseModel):
    id: str
    domain: str
    title: str
    source_name: str
    source_table: str
    publisher: str
    licence: str = "Government Open Data License - India"
    source_tier: Literal["A", "B"] = "B"
    adapter: str = "ogd_api"
    resource_id: str | None = None
    raw_file: str
    config_version: str
    retrieved: str
    caveats: list[str] = Field(default_factory=list)


class FlagPattern(BaseModel):
    """A published convention such as ``(29.5)`` meaning a caveated estimate."""

    name: str
    pattern: str
    flag: str
    strip: bool = True


class ReadSection(BaseModel):
    missing_markers: dict[str, str] = Field(default_factory=lambda: {"": "missing_in_source"})
    flag_patterns: list[FlagPattern] = Field(default_factory=list)
    strip_chars: list[str] = Field(default_factory=list)
    drop_columns: list[str] = Field(default_factory=list)
    dedupe_exact: bool = False


class IndicatorSpec(BaseModel):
    id: str
    label: str | None = None
    unit: str = "unknown"


class PeriodSpec(BaseModel):
    """How one value column maps to a period (used when columns are periods)."""

    type: Literal["month", "season", "calendar_year"]
    start_month: int
    end_month: int


class UnitRule(BaseModel):
    contains: str
    unit: str


class ValuesSection(BaseModel):
    mode: Literal["periods", "indicators"]
    # mode = periods: the indicator is fixed; columns are periods.
    indicator: IndicatorSpec | None = None
    # header regex: group 1 = start year; an optional group 2 = end-year suffix as published
    pattern: str | None = None
    period_columns: dict[str, PeriodSpec] = Field(default_factory=dict)
    # mode = indicators: columns are indicators.
    columns: dict[str, IndicatorSpec] = Field(default_factory=dict)
    remaining: bool = False  # every column without a role is an indicator
    id_prefix: str = ""
    unit_rules: list[UnitRule] = Field(default_factory=list)
    default_unit: str = "unknown"

    @model_validator(mode="after")
    def _check_mode(self) -> "ValuesSection":
        if self.mode == "periods" and self.indicator is None:
            msg = "values.mode = periods needs values.indicator"
            raise ValueError(msg)
        if self.mode == "periods" and not (self.pattern or self.period_columns):
            msg = "values.mode = periods needs values.pattern or values.period_columns"
            raise ValueError(msg)
        if self.mode == "indicators" and not (self.columns or self.remaining):
            msg = "values.mode = indicators needs values.columns or values.remaining"
            raise ValueError(msg)
        return self


class QuarterSpec(BaseModel):
    """One published quarter name: its label and the months it covers."""

    label: str  # for example "Q2"; the period label is "<year>-<label>"
    start_month: int = Field(ge=1, le=12)
    end_month: int = Field(ge=1, le=12)
    year_offset: int = 0  # calendar years added to the year column (fiscal quarters after December)


class YearConvention(BaseModel):
    """From this start year on, the year begins in ``start_month``."""

    from_year: int
    start_month: int = Field(ge=1, le=12)


class YearException(BaseModel):
    """One year whose bounds are stated outright (for example a transition year)."""

    year: int  # the start year as published
    start: str  # ISO date
    end: str  # ISO date

    @property
    def start_date(self) -> date:
        return date.fromisoformat(self.start)

    @property
    def end_date(self) -> date:
        return date.fromisoformat(self.end)

    @model_validator(mode="after")
    def _check_order(self) -> "YearException":
        if self.start_date > self.end_date:
            msg = f"period.exceptions: year {self.year} starts after it ends"
            raise ValueError(msg)
        return self


class PeriodSection(BaseModel):
    type: Literal["date", "calendar_year", "survey_year", "survey_round", "quarter"]
    start_month: int | None = None  # survey_year: month the year starts; must be stated
    date_format: str | None = None  # date: strptime format
    # survey_round: one fixed period for the whole table
    label: str | None = None
    start: str | None = None
    end: str | None = None
    # quarter: published quarter name -> label and months; needs period_year and
    # period_quarter columns
    quarter_map: dict[str, QuarterSpec] = Field(default_factory=dict)
    # Year windows that changed over time: later conventions apply from their first year on
    # and earlier years keep the window they were published with.
    conventions: list[YearConvention] = Field(default_factory=list)
    exceptions: list[YearException] = Field(default_factory=list)
    # Last start year for which a person confirmed the year window with the publisher.
    # Later periods are published with a warning until it is raised.
    verified_through: int | None = None
    # Periods absent between two that are present are reported. Always on for years and
    # quarters (consecutive) and for months and seasons (same slot, every year). True also
    # expects consecutive dates, for a source that should be daily; False turns it all off.
    expect_contiguous: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> "PeriodSection":
        if self.type == "quarter" and not self.quarter_map:
            msg = "period.type = quarter needs period.quarter_map"
            raise ValueError(msg)
        years = [c.from_year for c in self.conventions]
        if years != sorted(set(years)):
            msg = "period.conventions must be in increasing from_year order, without repeats"
            raise ValueError(msg)
        if self.conventions and self.type not in ("survey_year", "calendar_year"):
            msg = "period.conventions apply only to survey_year and calendar_year periods"
            raise ValueError(msg)
        if self.conventions and self.start_month is None:
            msg = "period.conventions need period.start_month for the years before the first one"
            raise ValueError(msg)
        return self

    @property
    def convention_summary(self) -> list[dict[str, int]]:
        """Window changes as plain facts for the catalogue."""
        return [{"from_year": c.from_year, "start_month": c.start_month} for c in self.conventions]


class GeoSection(BaseModel):
    level: Literal["national", "state", "district", "subdivision", "market"]
    vintage: str
    state_reference: str | None = "states"  # configs/reference/<name>.csv
    subdivision_reference: str | None = None
    # configs/reference/<name>.csv with alias, canonical, evidence; the file may be absent
    subdivision_alias_reference: str | None = "subdivision_aliases"
    total_members: list[str] = Field(default_factory=list)
    national_name: str = "India"


class Check(BaseModel):
    name: str
    kind: Literal["range", "order", "sum", "ratio", "bound_multiple", "unique_key"]
    flag: str = "inconsistent"
    indicators: list[str] = Field(default_factory=list)
    min: float | None = None
    max: float | None = None
    units: dict[str, list[float | None]] = Field(default_factory=dict)  # range by unit
    total: str | None = None
    parts: list[str] = Field(default_factory=list)
    numerator: str | None = None
    denominator: str | None = None
    target: str | None = None
    scale: float = 1.0
    atol: float = 0.0
    left: str | None = None
    right: str | None = None
    factor: float = 1.0
    columns: list[str] = Field(default_factory=list)


class ReconcileSection(BaseModel):
    """How far a new release may differ from the live one before a person must look."""

    max_revised_share: float = 0.10  # share of shared values that changed
    max_removed_share: float = 0.05  # share of earlier observations that vanished
    value_rtol: float = 1e-6


class RuleRef(BaseModel):
    id: str


class ViewDerived(BaseModel):
    name: str
    from_: Literal[
        "check_failed", "check_passed", "flag_in", "flag_equals", "period_valid", "constant"
    ] = Field(alias="from")
    checks: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    value: str | None = None

    model_config = {"populate_by_name": True}


class ViewSection(BaseModel):
    """How the agent-facing table is derived from the observation table."""

    mode: Literal["rows", "pivot_indicator", "pivot_period"]
    table: str  # name of the agent-facing table (the file the agent queries)
    columns: dict[str, str] = Field(default_factory=dict)  # legacy name -> obs column
    column_prefix: str = ""  # pivot_period: prefix added to the source period header
    lowercase: bool = False
    constants: dict[str, str] = Field(default_factory=dict)
    derived: list[ViewDerived] = Field(default_factory=list)
    sort: list[str] = Field(default_factory=list)
    int_columns: list[str] = Field(default_factory=list)
    date_columns: list[str] = Field(default_factory=list)
    row_flag: bool = True  # add the worst flag of the row as quality_flag
    attributes: list[str] = Field(default_factory=list)  # category/attribute columns kept


class SourceConfig(BaseModel):
    dataset: DatasetSection
    read: ReadSection = Field(default_factory=ReadSection)
    columns: dict[str, str] = Field(default_factory=dict)  # source header -> role
    values: ValuesSection
    period: PeriodSection
    geo: GeoSection
    rules: list[RuleRef] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    reconcile: ReconcileSection = Field(default_factory=ReconcileSection)
    view: ViewSection
    path: Path | None = None

    @property
    def dataset_id(self) -> str:
        return self.dataset.id

    @property
    def obs_table(self) -> str:
        return f"obs_{self.dataset.id}"


def load_source_config(path: Path) -> SourceConfig:
    """Read and validate one source configuration."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    config = SourceConfig.model_validate(data)
    config.path = path
    return config


def load_all(directory: Path = SOURCES_DIR) -> list[SourceConfig]:
    """Every configuration in a directory, sorted by dataset id."""
    configs = [load_source_config(path) for path in sorted(directory.glob("*.toml"))]
    return sorted(configs, key=lambda c: c.dataset_id)
