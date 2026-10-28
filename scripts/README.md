# Processed Data README

## Purpose

This project preprocesses two public Indian datasets for use in a curated analytical-data catalogue:

1. National Family Health Survey-5 district-level health indicators.
2. Daily Mandi commodity prices from Indian markets.

The original CSV files remain unchanged. Processed outputs are written to `data/processed/`.

## Source files

| Input file | Dataset | Main geography | Time coverage |
|---|---|---|---|
| `datafile.csv` | NFHS-5 India District Factsheet Data | District | 2019-2021 |
| `datafile2.csv` | Daily Mandi commodity prices | Market and district | Daily observations |

## Output files

| Output file | Description |
|---|---|
| `data/processed/nfhs5_district_indicators.parquet` | Long-format district health indicators from NFHS-5 |
| `data/processed/nfhs5_quality_report.csv` | NFHS row counts and data-quality summary |
| `data/processed/mandi_daily_prices.parquet` | Cleaned daily commodity-market price observations |
| `data/processed/mandi_quality_report.csv` | Mandi row counts and validation summary |

## NFHS-5 preprocessing

### 1. Text cleaning

Leading and trailing spaces, repeated internal spaces, and non-breaking spaces are removed from column names and text fields.

### 2. Geographic standardization

The source district and state/UT names are retained in `district_name_source` and `state_name_source`.

A standardized state field, `state_name`, is also created. Known aliases are mapped where safe, for example:

- `Keralam` becomes `Kerala`
- `Orissa` becomes `Odisha`
- `Pondicherry` becomes `Puducherry`

The original value is never overwritten.

### 3. Sample-size conversion

The following fields are converted from text to numeric values:

- `sample_households`
- `sample_women_15_49`
- `sample_men_15_54`

These sample sizes remain associated with each district indicator so users can assess reliability.

### 4. Wide-to-long transformation

The original NFHS file has one row per district and many health-indicator columns. It is converted to one row per district-indicator combination.

The processed structure is:

```text
state_name | district_name | indicator_id | indicator_label | value | unit
```

This makes filtering, comparisons, rankings, and chart generation consistent across all health indicators.

### 5. Value parsing and quality flags

| Original value pattern | Processed treatment |
|---|---|
| `78.0` | Converted to numeric value `78.0` |
| `(29.5)` | Converted to numeric value `29.5`; marked `low_sample_estimate` |
| `*` | Stored as missing; marked `suppressed` |
| blank or invalid text | Stored as missing; marked `missing_or_unparseable` |

### 6. Unit assignment

The script labels common units using the indicator text:

- values containing `%` become `percent`;
- values containing `per 1,000` become `per_1000_males`;
- rupee expenditure indicators become `INR`;
- survey-count fields become `count`;
- anything not safely identified is labelled `unknown`.

### 7. Source metadata

Each processed NFHS row contains:

```text
source_name = National Family Health Survey-5
source_table = India Districts Factsheet Data
survey_round = NFHS-5
survey_period = 2019-2021
geography_level = district
```

## Mandi-price preprocessing

### 1. Column renaming

The raw encoded price columns are renamed:

| Raw column | Processed column |
|---|---|
| `Min_x0020_Price` | `min_price_inr_per_quintal` |
| `Max_x0020_Price` | `max_price_inr_per_quintal` |
| `Modal_x0020_Price` | `modal_price_inr_per_quintal` |

### 2. Date conversion

`Arrival_Date` is parsed as a real date using the source format `DD/MM/YYYY`.

The source date text is preserved in `arrival_date_raw`.

### 3. Numeric price conversion

Minimum, maximum, and modal prices are converted to numeric values after commas and spaces are removed.

All prices are labelled:

```text
price_unit = INR_per_quintal
```

### 4. Duplicate removal

Exact duplicate records are removed using the combination of:

```text
state, district, market, commodity, variety, grade,
arrival_date, minimum price, maximum price, modal price
```

### 5. Validation checks

Every Mandi row receives these validation fields:

| Field | Meaning |
|---|---|
| `is_arrival_date_valid` | Arrival date was successfully parsed |
| `is_price_non_negative` | All three prices are zero or greater |
| `is_price_order_valid` | Minimum price ≤ modal price ≤ maximum price |
| `quality_flag` | Overall data-quality outcome |

Possible `quality_flag` values are:

```text
reported
invalid_arrival_date
negative_or_missing_price
invalid_price_order
```

Rows with quality problems are retained for auditability. They should be excluded or handled explicitly when answering questions.

## Recommended query rules

- Do not treat suppressed NFHS values as zero.
- Show a caveat when an NFHS estimate has `is_low_sample_estimate = true`.
- Use NFHS only for the 2019-2021 survey period unless another compatible survey round is added.
- Use Mandi prices only when `quality_flag = reported`.
- Do not average Mandi market prices across markets unless the aggregation method and weighting basis are explicitly defined.
- Preserve the original source names alongside standardized names in evidence panels.

## Data-quality principle

The preprocessing pipeline preserves original values and records uncertainty instead of hiding it. This supports the project requirement that the agent should decline, qualify, or explain results when the data cannot safely answer a question.