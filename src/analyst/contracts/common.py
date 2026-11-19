"""Common types (design document Section 4.1)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

GeoLevel = Literal["national", "state", "district", "subdivision", "market"]
PeriodType = Literal[
    "date",
    "month",
    "quarter",
    "season",
    "calendar_year",
    "survey_year",
    "survey_round",
    "fiscal_year",
    "agri_year",
]
QualityFlag = Literal[
    "reported",
    "low_sample_estimate",
    "implausible",
    "inconsistent",
    "out_of_range",
    "suppressed",
    "missing_in_source",
    "unparsed",
    "revised",
    "provisional",
]


class Contract(BaseModel):
    """Every contract is frozen and forbids extra fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Place(Contract):
    """A place mention resolved to a geography code, level and canonical name."""

    requested: str
    level: GeoLevel
    code: str
    name: str
    match: Literal["exact", "alias"]
    vintage: str | None = None


class PeriodWindow(Contract):
    """A period mention resolved to a typed date window, noting any default that was applied."""

    requested: str
    type: PeriodType
    label: str
    start: date
    end: date
    default_applied: str | None = None


class IndicatorRef(Contract):
    """An indicator chosen from the catalogue, with its label and unit."""

    indicator_id: str
    label: str
    unit: str


class CellRef(Contract):
    """A reference to one cell of a query result by row index and column name."""

    row: int
    column: str


class Assumption(Contract):
    """An assumption the agent made in reading the question, with a stable code."""

    code: str
    text: str


class Caveat(Contract):
    """A caveat shown with an answer and where it came from."""

    code: str
    text: str
    source: Literal["catalogue", "flag", "check", "statistical", "coverage"]
