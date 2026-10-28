from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd


RAW_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/processed")

NFHS_INPUT = "../data/raw/datafile1.csv"
MANDI_INPUT = "../data/raw/datafile2.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    value = str(value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value if value else pd.NA


def slug_with_hash(text: str, prefix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{slug[:90]}_{digest}"


def parse_nfhs_value(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    raw = series.astype("string").str.strip()

    suppressed = raw.eq("*")
    low_sample = raw.str.match(r"^\(.*\)$", na=False)

    numeric_text = (
        raw.str.replace(r"^\((.*)\)$", r"\1", regex=True)
        .str.replace(",", "", regex=False)
        .str.replace("*", "", regex=False)
        .str.strip()
    )

    values = pd.to_numeric(numeric_text, errors="coerce")
    values = values.mask(suppressed)

    return values, suppressed, low_sample


def nfhs_unit(indicator: str) -> str:
    indicator_lower = indicator.lower()

    if "%" in indicator:
        return "percent"
    if "per 1,000" in indicator_lower:
        return "per_1000_males"
    if "(rs." in indicator_lower or "rs.)" in indicator_lower:
        return "INR"
    if "number of" in indicator_lower:
        return "count"

    return "unknown"


def standardize_state_name(series: pd.Series) -> pd.Series:
    aliases = {
        "Andaman & Nicobar Islands": "Andaman and Nicobar Islands",
        "Dadra & Nagar Haveli and Daman & Diu": "Dadra and Nagar Haveli and Daman and Diu",
        "NCT of Delhi": "Delhi",
        "Orissa": "Odisha",
        "Pondicherry": "Puducherry",
        "Uttaranchal": "Uttarakhand",
        "Keralam": "Kerala",
    }
    return series.replace(aliases)


# -------------------------------------------------------------------
# 1. NFHS-5 district factsheet data
# -------------------------------------------------------------------
nfhs = pd.read_csv(NFHS_INPUT, dtype="string", keep_default_na=False)
nfhs.columns = [clean_text(column) for column in nfhs.columns]

nfhs = nfhs.apply(lambda column: column.map(clean_text))

district_column = "District Names"
state_column = "State/UT"
sample_columns = [
    "Number of Households surveyed",
    "Number of Women age 15-49 years interviewed",
    "Number of Men age 15-54 years interviewed",
]

required_nfhs_columns = [district_column, state_column, *sample_columns]
missing_nfhs_columns = [
    column for column in required_nfhs_columns if column not in nfhs.columns
]
if missing_nfhs_columns:
    raise ValueError(f"NFHS columns not found: {missing_nfhs_columns}")

nfhs = nfhs.rename(
    columns={
        district_column: "district_name_source",
        state_column: "state_name_source",
        "Number of Households surveyed": "sample_households",
        "Number of Women age 15-49 years interviewed": "sample_women_15_49",
        "Number of Men age 15-54 years interviewed": "sample_men_15_54",
    }
)

for sample_column in [
    "sample_households",
    "sample_women_15_49",
    "sample_men_15_54",
]:
    nfhs[sample_column] = pd.to_numeric(
        nfhs[sample_column].str.replace(",", "", regex=False),
        errors="coerce",
    ).astype("Int64")

nfhs["state_name"] = standardize_state_name(nfhs["state_name_source"])
nfhs["district_name"] = nfhs["district_name_source"]

id_columns = [
    "district_name_source",
    "district_name",
    "state_name_source",
    "state_name",
    "sample_households",
    "sample_women_15_49",
    "sample_men_15_54",
]

indicator_columns = [
    column for column in nfhs.columns if column not in id_columns
]

nfhs_long = nfhs.melt(
    id_vars=id_columns,
    value_vars=indicator_columns,
    var_name="indicator_label",
    value_name="value_raw",
)

nfhs_long["indicator_label"] = nfhs_long["indicator_label"].map(clean_text)
nfhs_long["indicator_id"] = nfhs_long["indicator_label"].map(
    lambda label: slug_with_hash(str(label), "nfhs5")
)

(
    nfhs_long["value"],
    nfhs_long["is_suppressed"],
    nfhs_long["is_low_sample_estimate"],
) = parse_nfhs_value(nfhs_long["value_raw"])

nfhs_long["unit"] = nfhs_long["indicator_label"].map(nfhs_unit)
nfhs_long["source_name"] = "National Family Health Survey-5"
nfhs_long["source_table"] = "India Districts Factsheet Data"
nfhs_long["survey_round"] = "NFHS-5"
nfhs_long["survey_period"] = "2019-2021"
nfhs_long["geography_level"] = "district"
nfhs_long["quality_flag"] = np.select(
    [
        nfhs_long["is_suppressed"],
        nfhs_long["is_low_sample_estimate"],
        nfhs_long["value"].isna(),
    ],
    [
        "suppressed",
        "low_sample_estimate",
        "missing_or_unparseable",
    ],
    default="reported",
)

nfhs_long = nfhs_long[
    [
        "source_name",
        "source_table",
        "survey_round",
        "survey_period",
        "geography_level",
        "state_name_source",
        "state_name",
        "district_name_source",
        "district_name",
        "indicator_id",
        "indicator_label",
        "value",
        "unit",
        "is_suppressed",
        "is_low_sample_estimate",
        "quality_flag",
        "sample_households",
        "sample_women_15_49",
        "sample_men_15_54",
        "value_raw",
    ]
].sort_values(["state_name", "district_name", "indicator_id"])

nfhs_long.to_parquet(
    "../data/processed/nfhs5_district_indicators.parquet",
    index=False,
)

nfhs_quality = pd.DataFrame(
    {
        "metric": [
            "input_rows",
            "output_rows",
            "districts",
            "states_uts",
            "suppressed_values",
            "low_sample_estimates",
            "missing_or_unparseable_values",
        ],
        "value": [
            len(nfhs),
            len(nfhs_long),
            nfhs_long["district_name"].nunique(),
            nfhs_long["state_name"].nunique(),
            int(nfhs_long["is_suppressed"].sum()),
            int(nfhs_long["is_low_sample_estimate"].sum()),
            int((nfhs_long["quality_flag"] == "missing_or_unparseable").sum()),
        ],
    }
)
nfhs_quality.to_csv("../data/processed/nfhs5_quality_report.csv", index=False)


# -------------------------------------------------------------------
# 2. Daily Mandi commodity prices
# -------------------------------------------------------------------
mandi = pd.read_csv(MANDI_INPUT, dtype="string", keep_default_na=False)
mandi.columns = [clean_text(column) for column in mandi.columns]
mandi = mandi.apply(lambda column: column.map(clean_text))

mandi_column_mapping = {
    "State": "state_name_source",
    "District": "district_name_source",
    "Market": "market_name",
    "Commodity": "commodity_name",
    "Variety": "variety",
    "Grade": "grade",
    "Arrival_Date": "arrival_date_raw",
    "Min_x0020_Price": "min_price_inr_per_quintal",
    "Max_x0020_Price": "max_price_inr_per_quintal",
    "Modal_x0020_Price": "modal_price_inr_per_quintal",
}

missing_mandi_columns = [
    source_column
    for source_column in mandi_column_mapping
    if source_column not in mandi.columns
]
if missing_mandi_columns:
    raise ValueError(f"Mandi columns not found: {missing_mandi_columns}")

mandi = mandi.rename(columns=mandi_column_mapping)

mandi["state_name"] = standardize_state_name(mandi["state_name_source"])
mandi["district_name"] = mandi["district_name_source"]

mandi["arrival_date"] = pd.to_datetime(
    mandi["arrival_date_raw"],
    format="%d/%m/%Y",
    errors="coerce",
)

for price_column in [
    "min_price_inr_per_quintal",
    "max_price_inr_per_quintal",
    "modal_price_inr_per_quintal",
]:
    mandi[price_column] = pd.to_numeric(
        mandi[price_column].str.replace(",", "", regex=False),
        errors="coerce",
    )

mandi["price_unit"] = "INR_per_quintal"
mandi["source_name"] = "Current daily price of various commodities from various markets (Mandi)"
mandi["source_table"] = "AGMARKNET daily market prices"
mandi["geography_level"] = "market"

mandi["is_price_non_negative"] = (
    mandi[
        [
            "min_price_inr_per_quintal",
            "max_price_inr_per_quintal",
            "modal_price_inr_per_quintal",
        ]
    ]
    .ge(0)
    .all(axis=1)
)

mandi["is_price_order_valid"] = (
    mandi["min_price_inr_per_quintal"].le(mandi["modal_price_inr_per_quintal"])
    & mandi["modal_price_inr_per_quintal"].le(mandi["max_price_inr_per_quintal"])
)

mandi["is_arrival_date_valid"] = mandi["arrival_date"].notna()

mandi["quality_flag"] = np.select(
    [
        ~mandi["is_arrival_date_valid"],
        ~mandi["is_price_non_negative"],
        ~mandi["is_price_order_valid"],
    ],
    [
        "invalid_arrival_date",
        "negative_or_missing_price",
        "invalid_price_order",
    ],
    default="reported",
)

mandi = mandi.drop_duplicates(
    subset=[
        "state_name",
        "district_name",
        "market_name",
        "commodity_name",
        "variety",
        "grade",
        "arrival_date",
        "min_price_inr_per_quintal",
        "max_price_inr_per_quintal",
        "modal_price_inr_per_quintal",
    ]
)

mandi = mandi[
    [
        "source_name",
        "source_table",
        "geography_level",
        "state_name_source",
        "state_name",
        "district_name_source",
        "district_name",
        "market_name",
        "commodity_name",
        "variety",
        "grade",
        "arrival_date",
        "min_price_inr_per_quintal",
        "max_price_inr_per_quintal",
        "modal_price_inr_per_quintal",
        "price_unit",
        "is_arrival_date_valid",
        "is_price_non_negative",
        "is_price_order_valid",
        "quality_flag",
        "arrival_date_raw",
    ]
].sort_values(
    [
        "arrival_date",
        "state_name",
        "district_name",
        "market_name",
        "commodity_name",
    ]
)

mandi.to_parquet(
    "../data/processed/mandi_daily_prices.parquet",
    index=False,
)

mandi_quality = pd.DataFrame(
    {
        "metric": [
            "input_rows",
            "output_rows_after_exact_deduplication",
            "states",
            "districts",
            "markets",
            "commodities",
            "invalid_arrival_dates",
            "negative_or_missing_prices",
            "invalid_price_order_rows",
        ],
        "value": [
            len(pd.read_csv(MANDI_INPUT, dtype="string")),
            len(mandi),
            mandi["state_name"].nunique(),
            mandi["district_name"].nunique(),
            mandi["market_name"].nunique(),
            mandi["commodity_name"].nunique(),
            int((mandi["quality_flag"] == "invalid_arrival_date").sum()),
            int((mandi["quality_flag"] == "negative_or_missing_price").sum()),
            int((mandi["quality_flag"] == "invalid_price_order").sum()),
        ],
    }
)
mandi_quality.to_csv("../data/processed/mandi_quality.csv", index=False)