# Processed Data README

## Purpose

This project preprocesses three public Indian datasets for use in a curated analytical-data catalogue:

1. National Family Health Survey-5 district-level health indicators.
2. Daily Mandi commodity prices from Indian markets.
3. National Crime Records Bureau (NCRB) annual crime statistics for India.

The original CSV files remain unchanged. Processed outputs are written to `data/processed/`.

## Source files

| Input file | Dataset | Main geography | Time coverage |
|---|---|---|---|
| `data/raw/datafile1.csv` | NFHS-5 India District Factsheet Data | District | 2019-2021 |
| `data/raw/datafile2.csv` | Daily Mandi commodity prices | Market and district | Daily observations |
| `data/raw/datafile3.csv` | NCRB CII 2024 Table 1.1(ii), annual crime statistics | National (India) | 2022-2024, as supplied in the CSV |

Run from any directory: `python scripts/preprocess_data.py`. The NFHS-5 and Mandi
files are downloaded by `python scripts/download_raw.py`.

## Output files

| Output file | Description |
|---|---|
| `data/processed/nfhs5_district_indicators.parquet` | Long-format district health indicators from NFHS-5 |
| `data/processed/nfhs5_quality_report.csv` | NFHS row counts and data-quality summary |
| `data/processed/mandi_daily_prices.parquet` | Cleaned daily commodity-market price observations |
| `data/processed/mandi_quality_report.csv` | Mandi row counts and validation summary |
| `data/processed/ncrb_annual_crime_statistics.csv` | Cleaned NCRB annual crime statistics in CSV format |
| `data/processed/ncrb_annual_crime_statistics.parquet` | Cleaned NCRB annual crime statistics in Parquet format, if a Parquet engine is installed |
| `data/processed/ncrb_quality_report.csv` | NCRB row counts and validation summary |

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

## NCRB annual crime-statistics preprocessing

### 1. Source and geographic level

The input file is `data/raw/datafile3.csv` (published as `NCRB_CII_2024_Table_1.1.ii.csv`), corresponding to NCRB CII 2024 Table 1.1(ii).

The supplied file contains annual observations for India. The processed rows are labelled:

```text
source_name = National Crime Records Bureau (NCRB)
source_table = CII 2024 Table 1.1(ii)
geography_level = national
country = India
```

The data should not be treated as state-, district-, or police-station-level data.

### 2. Column standardization

The original column names are mapped to consistent snake-case names:

| Source column | Processed column |
|---|---|
| `Year` | `year` |
| `Mid-Year Projected Population (in Lakhs)` | `population_lakhs` |
| `Crime Incidence - IPC/BNS` | `ipc_bns_crime_count` |
| `Crime Incidence - SLL` | `sll_crime_count` |
| `Crime Incidence - Total` | `total_crime_count` |
| `Crime Rate - IPC/BNS` | `ipc_bns_crime_rate` |
| `Crime Rate - SLL` | `sll_crime_rate` |
| `Crime Rate - Total` | `total_crime_rate` |
| `Percentage of IPC/BNS Crimes to Total Cognizable Crimes` | `ipc_bns_percentage` |

The preprocessing raises an error if any expected source column is absent. This prevents silently processing a structurally different file.

### 3. Numeric conversion

The year, population, crime incidence, crime rates, and percentage fields are converted from text to numeric values. Commas are removed before conversion.

The `year` field is stored as a nullable integer. Values that cannot be parsed become missing rather than being silently replaced with zero.

`population_lakhs` remains expressed in lakhs of people. The source crime-rate fields are retained as reported.

### 4. Validation checks

The pipeline creates the following validation fields:

| Field | Meaning |
|---|---|
| `has_missing_values` | At least one expected numeric field is missing or could not be parsed |
| `has_negative_values` | At least one population, count, rate, or percentage field is negative |
| `incidence_total_valid` | IPC/BNS incidence plus SLL incidence equals total incidence |
| `ipc_bns_percentage_valid` | Reported IPC/BNS percentage is within 0.15 percentage points of the percentage implied by the counts |
| `ipc_bns_crime_rate_valid` | Reported IPC/BNS crime rate is within 0.15 of count divided by population in lakhs |
| `sll_crime_rate_valid` | Reported SLL crime rate is within 0.15 of count divided by population in lakhs |
| `total_crime_rate_valid` | Reported total crime rate is within 0.15 of count divided by population in lakhs |
| `is_duplicate_year` | The year appears more than once in the input |

The rate check uses the following relationship when population is expressed in lakhs:

```text
crime rate = crime count / population_lakhs
```

This corresponds to a rate per 100,000 people. The tolerance is intended to allow for rounding in published values. Confirm the source table's exact rate definition and rounding convention before relying on these checks as definitive.

The percentage check compares the reported percentage with:

```text
IPC/BNS crime incidence / total crime incidence * 100
```

This check assumes that the numerator and denominator in the source percentage use those same incidence definitions. Verify that assumption against the source table notes before interpreting a failed check.

### 5. Overall quality flag

The `quality_flag` field summarizes row-level checks using the following values:

| `quality_flag` | Meaning |
|---|---|
| `passed` | No missing values, negative values, duplicate year, or failed validation checks were detected |
| `missing_or_unparseable` | At least one expected numeric field is missing or unparseable |
| `negative_values` | At least one checked numeric value is negative |
| `duplicate_year` | The year occurs more than once |
| `validation_failed` | At least one incidence, percentage, or crime-rate validation failed |

The pipeline retains records with quality problems so that they can be audited. The flag is a screening aid, not a guarantee that a row is correct. Review the individual validation fields and the source documentation before using a flagged observation.

### 6. Quality report

`ncrb_quality_report.csv` summarizes input and output row counts, unique years, missing values, negative values, duplicate years, failed incidence/percentage/rate checks, and rows passing all checks.

The cleaned CSV is written even when a Parquet engine is unavailable. To write the Parquet output, install a compatible engine such as `pyarrow`.

## Recommended query rules

- Do not treat suppressed NFHS values as zero.
- Show a caveat when an NFHS estimate has `is_low_sample_estimate = true`.
- Use NFHS only for the 2019-2021 survey period unless another compatible survey round is added.
- Use Mandi prices only when `quality_flag = reported`.
- Do not average Mandi market prices across markets unless the aggregation method and weighting basis are explicitly defined.
- Preserve the original source names alongside standardized names in evidence panels.
- Use NCRB statistics only at the national level represented by the source data; do not infer state- or district-level crime patterns from national totals.
- Check the NCRB row's `quality_flag` and individual validation fields before using it. Explain failed checks and do not silently treat missing or invalid values as zero.
- Preserve the distinction between IPC/BNS incidence, SLL incidence, total incidence, crime rates, and percentages. Do not combine counts and rates in the same aggregation.
- When comparing years, confirm that the source definitions and reporting framework are comparable across the selected years. The source's IPC/BNS label should be preserved as reported.

## Data-quality principle

The preprocessing pipeline preserves original values and records uncertainty instead of hiding it. This supports the project requirement that the agent should decline, qualify, or explain results when the data cannot safely answer a question.
