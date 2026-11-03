"""Validation of an observation table: a Pandera schema built from the configuration.

Lazy validation reports every failing value at once; each failed rule becomes a
blocking review item. The rules are the publication invariants of the data contract
that can be checked on one table (uniqueness, flags and values agreeing, periods in
order, closed vocabularies).
"""

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from analyst.data.config import SourceConfig
from analyst.data.contract import EMPTY_VALUE_FLAGS, FLAG_RANK, GEO_MATCH, PERIOD_TYPES, ReviewItem


def category_columns(config: SourceConfig) -> list[str]:
    return [role.split(":")[1] for role in config.columns.values() if role.startswith("category:")]


def key_columns(config: SourceConfig) -> list[str]:
    """Columns that identify one observation."""
    return ["geo_code", "period_type", "period_label", "indicator_id", *category_columns(config)]


def build_schema(config: SourceConfig) -> pa.DataFrameSchema:
    key = key_columns(config)
    return pa.DataFrameSchema(
        {
            "dataset_id": pa.Column(nullable=False),
            "geo_code": pa.Column(nullable=False),
            "indicator_id": pa.Column(nullable=False),
            "unit": pa.Column(nullable=False),
            "quality_flag": pa.Column(
                nullable=False,
                checks=pa.Check.isin(list(FLAG_RANK), name="flag_in_vocabulary"),
            ),
            "geo_match": pa.Column(
                nullable=False,
                checks=pa.Check.isin(list(GEO_MATCH), name="geo_match_in_vocabulary"),
            ),
            "period_type": pa.Column(
                nullable=False, checks=pa.Check.isin(list(PERIOD_TYPES), name="period_type_known")
            ),
        },
        checks=[
            pa.Check(
                lambda df: df["value"].isna() == df["quality_flag"].isin(EMPTY_VALUE_FLAGS),
                name="value_empty_exactly_when_flag_says_so",
            ),
            pa.Check(
                lambda df: ~(df["period_start"] > df["period_end"]),
                name="period_start_not_after_end",
            ),
            pa.Check(
                lambda df: df["period_start"].notna() | (df["quality_flag"] == "unparsed"),
                name="period_present_unless_unparsed",
            ),
            pa.Check(
                lambda df: ~df.duplicated(subset=key, keep=False),
                name="observation_key_unique",
            ),
        ],
        strict=False,
    )


def validate_obs(config: SourceConfig, obs: pd.DataFrame) -> list[ReviewItem]:
    """Blocking review items for every schema rule the table breaks."""
    if obs.empty:
        return []
    try:
        build_schema(config).validate(obs, lazy=True)
    except SchemaErrors as errors:
        cases = errors.failure_cases
        items = []
        for check, group in cases.groupby("check", dropna=False):
            rows = int(group["index"].nunique()) if group["index"].notna().any() else len(group)
            duplicate = check == "observation_key_unique"
            items.append(
                ReviewItem(
                    dataset_id=config.dataset_id,
                    severity="block",
                    kind="duplicate_key" if duplicate else "schema_violation",
                    detail=(
                        f"{rows} values share one observation key {key_columns(config)}"
                        if duplicate
                        else f"rule {check!r} fails"
                    ),
                    count=rows,
                    suggestion=(
                        "check the source for repeated rows; remove only exact copies"
                        if duplicate
                        else "inspect the rows reported for this rule; fix the source or config"
                    ),
                )
            )
        return items
    return []
