"""The data contract: the one output shape every prepared table follows (version 1.1).

Consumers (agent tools, routing-data generator, evaluation sets) depend on these
names only, never on how a table was produced. Every dataset is published as
``obs_<dataset>``: one row per value, with the value's place, period and indicator
as columns, plus dataset-specific category and attribute columns.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = "1.1"


class Flag(StrEnum):
    """Quality flag of one value, in order of priority (highest first)."""

    UNPARSED = "unparsed"
    MISSING_IN_SOURCE = "missing_in_source"
    SUPPRESSED = "suppressed"
    OUT_OF_RANGE = "out_of_range"
    INCONSISTENT = "inconsistent"
    IMPLAUSIBLE = "implausible"
    LOW_SAMPLE_ESTIMATE = "low_sample_estimate"
    REVISED = "revised"
    PROVISIONAL = "provisional"
    REPORTED = "reported"


FLAG_RANK = {flag.value: rank for rank, flag in enumerate(Flag)}
# The value is empty exactly when its flag is one of these.
EMPTY_VALUE_FLAGS = frozenset(
    {Flag.UNPARSED.value, Flag.MISSING_IN_SOURCE.value, Flag.SUPPRESSED.value}
)
GEO_MATCH = ("exact", "alias", "unmatched")
PERIOD_TYPES = (
    "date",
    "month",
    "quarter",
    "season",
    "calendar_year",
    "survey_year",
    "survey_round",
)

# Columns present in every observation table, in this order. Dataset-specific
# category and attribute columns follow after ``period_source``.
OBS_HEAD = [
    "dataset_id",
    "dataset_version",
    "source_row",
    "geo_level",
    "geo_code",
    "geo_name",
    "geo_name_source",
    "geo_state",
    "geo_state_source",
    "geo_district",
    "geo_district_source",
    "geo_vintage",
    "geo_match",
    "is_total_row",
    "period_type",
    "period_label",
    "period_source",
    "period_start",
    "period_end",
    "indicator_id",
    "indicator_label_source",
]
OBS_TAIL = ["value", "unit", "value_raw", "quality_flag", "rule_ids", "checks_failed"]

Severity = Literal["block", "warn", "info"]


class ReviewItem(BaseModel):
    """One thing a person must decide on (block, warn) or may ignore (info)."""

    dataset_id: str
    severity: Severity
    kind: str
    detail: str
    count: int = 0
    suggestion: str = ""


class CatalogueEntry(BaseModel):
    """Facts about one published table, recomputed from the data on every release."""

    dataset_id: str
    dataset_version: str
    config_version: str
    domain: str
    title: str
    source_name: str
    source_table: str
    publisher: str
    licence: str
    retrieved: str
    raw_sha256: str
    obs_table: str
    agent_table: str
    rows: int
    geo_levels: list[str]
    geo_vintage: str
    period_types: list[str]
    period_start_month: int | None = None
    period_conventions: list[dict[str, Any]] = Field(default_factory=list)
    coverage_start: str
    coverage_end: str
    indicators: int
    indicator_units: dict[str, str]
    categories: dict[str, int] = Field(default_factory=dict)
    has_total_rows: bool
    flag_counts: dict[str, int]
    caveats: list[str] = Field(default_factory=list)
