# Milestone 2 EDA summary

Produced by `scripts/eda_tables.py`.

## Table profiles

| Table | Rows | Columns | Missing cells | Exact duplicate rows | Duplicate keys |
| --- | --- | --- | --- | --- | --- |
| `imd_subdivision_monthly_rainfall` | 4,188 | 19 | 134 | 0 | 0 |
| `plfs_state_ur_usual_status` | 38 | 6 | 4 | 0 | 0 |
| `nfhs5_district_indicators` | 73,528 | 20 | 4,132 | 0 | 0 |
| `mandi_daily_prices` | 16,393 | 22 | 0 | 0 | 0 |
| `ncrb_annual_crime_statistics` | 3 | 22 | 0 | 0 | 0 |

## Numeric columns (count, mean, std, min, median, max, IQR outliers)

### `imd_subdivision_monthly_rainfall`

| Column | Count | Mean | Std | Min | Median | Max | IQR outliers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| year | 4,188 | 1959.22 | 33.72 | 1901.00 | 1959.00 | 2017.00 | 0 |
| jan | 4,184 | 18.94 | 33.79 | 0.00 | 5.95 | 583.70 | 404 |
| feb | 4,185 | 21.60 | 35.73 | 0.00 | 6.50 | 403.50 | 397 |
| mar | 4,182 | 27.41 | 46.93 | 0.00 | 7.90 | 605.60 | 477 |
| apr | 4,184 | 43.07 | 68.15 | 0.00 | 15.45 | 595.10 | 461 |
| may | 4,185 | 85.66 | 122.70 | 0.00 | 36.90 | 1168.60 | 523 |
| jun | 4,183 | 230.12 | 234.29 | 0.40 | 138.80 | 1609.90 | 313 |
| jul | 4,181 | 347.02 | 268.85 | 0.00 | 285.00 | 2362.80 | 293 |
| aug | 4,184 | 289.74 | 188.43 | 0.00 | 258.50 | 1664.60 | 139 |
| sep | 4,182 | 197.32 | 135.55 | 0.10 | 173.70 | 1222.00 | 125 |
| oct | 4,181 | 95.32 | 99.19 | 0.00 | 65.20 | 948.30 | 109 |
| nov | 4,177 | 39.50 | 68.36 | 0.00 | 9.40 | 648.90 | 471 |
| dec | 4,178 | 18.97 | 43.05 | 0.00 | 3.00 | 617.50 | 537 |
| annual | 4,162 | 1409.45 | 902.60 | 62.30 | 1120.35 | 6331.10 | 401 |
| jf | 4,182 | 40.52 | 59.29 | 0.00 | 18.90 | 699.50 | 363 |
| mam | 4,179 | 155.82 | 201.20 | 0.00 | 74.80 | 1745.80 | 418 |
| jjas | 4,178 | 1063.85 | 706.67 | 57.40 | 880.60 | 4536.90 | 302 |
| ond | 4,175 | 153.65 | 166.86 | 0.00 | 97.70 | 1252.50 | 247 |

### `plfs_state_ur_usual_status`

| Column | Count | Mean | Std | Min | Median | Max | IQR outliers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fy_2017_18 | 37 | 7.64 | 4.58 | 0.40 | 7.00 | 21.40 | 3 |
| fy_2018_19 | 37 | 7.32 | 5.30 | 0.00 | 6.70 | 31.60 | 2 |
| fy_2019_20 | 38 | 6.16 | 4.32 | 0.10 | 5.20 | 25.70 | 2 |
| fy_2020_21 | 37 | 5.40 | 3.48 | 1.10 | 4.60 | 19.20 | 2 |
| fy_2021_22 | 37 | 5.48 | 3.18 | 1.60 | 4.80 | 17.20 | 2 |

### `nfhs5_district_indicators`

| Column | Count | Mean | Std | Min | Median | Max | IQR outliers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| value | 69,396 | 94.97 | 452.67 | 0.00 | 33.00 | 20101.00 | 2,120 |
| sample_households | 73,528 | 900.50 | 69.22 | 213.00 | 908.00 | 990.00 | 3,224 |
| sample_women_15_49 | 73,528 | 1024.02 | 176.94 | 216.00 | 1020.00 | 1621.00 | 1,248 |
| sample_men_15_54 | 73,528 | 144.00 | 31.93 | 17.00 | 145.00 | 241.00 | 1,560 |

### `mandi_daily_prices`

| Column | Count | Mean | Std | Min | Median | Max | IQR outliers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| min_price_inr_per_quintal | 16,393 | 5078.41 | 5463.59 | 0.01 | 3800.00 | 112300.00 | 1,004 |
| max_price_inr_per_quintal | 16,393 | 7907.44 | 234385.43 | 0.01 | 4500.00 | 30002800.00 | 1,144 |
| modal_price_inr_per_quintal | 16,393 | 5604.45 | 5938.46 | 0.01 | 4000.00 | 125000.00 | 1,035 |

### `ncrb_annual_crime_statistics`

| Column | Count | Mean | Std | Min | Median | Max | IQR outliers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| year | 3 | 2023.00 | 1.00 | 2022.00 | 2023.00 | 2024.00 | 0 |
| population_lakhs | 3 | 13923.30 | 125.80 | 13797.50 | 13923.30 | 14049.10 | 0 |
| ipc_bns_crime_count | 3 | 3623029.67 | 121595.68 | 3544608.00 | 3561379.00 | 3763102.00 | 0 |
| sll_crime_count | 3 | 2361097.67 | 108814.90 | 2263567.00 | 2341259.00 | 2478467.00 | 0 |
| total_crime_count | 3 | 5984127.33 | 225022.22 | 5824946.00 | 5885867.00 | 6241569.00 | 0 |
| ipc_bns_crime_rate | 3 | 260.23 | 9.19 | 252.30 | 258.10 | 270.30 | 0 |
| sll_crime_rate | 3 | 169.57 | 7.41 | 164.10 | 166.60 | 178.00 | 0 |
| total_crime_rate | 3 | 429.80 | 16.11 | 418.90 | 422.20 | 448.30 | 0 |
| ipc_bns_percentage | 3 | 60.54 | 0.49 | 60.22 | 60.29 | 61.10 | 0 |

## Missing values per column (non-zero only)

- `imd_subdivision_monthly_rainfall`: jan 4 (0.1%), feb 3 (0.1%), mar 6 (0.1%), apr 4 (0.1%), may 3 (0.1%), jun 5 (0.1%), jul 7 (0.2%), aug 4 (0.1%), sep 6 (0.1%), oct 7 (0.2%), nov 11 (0.3%), dec 10 (0.2%), annual 26 (0.6%), jf 6 (0.1%), mam 9 (0.2%), jjas 10 (0.2%), ond 13 (0.3%)
- `plfs_state_ur_usual_status`: fy_2017_18 1 (2.6%), fy_2018_19 1 (2.6%), fy_2020_21 1 (2.6%), fy_2021_22 1 (2.6%)
- `nfhs5_district_indicators`: value 4,132 (5.6%)
- `mandi_daily_prices`: none
- `ncrb_annual_crime_statistics`: none

## NFHS-5 quality flags

- reported: 64,512 (87.7%)
- low_sample_estimate: 4,884 (6.6%)
- suppressed: 4,132 (5.6%)
- distinct indicators: 104
- distinct (state, district) pairs: 707

NFHS-5 correlation matrix computed over 707 districts for 6 indicators (figure `nfhs_correlation.png`).

## Mandi snapshot

- arrival dates: 2026-10-29 to 2026-10-29
- states 29, markets 1,725, commodities 261
- rows where min = modal = max price: 3,598

## Routing label distribution

| `tool` | train | calibration | dev_synthetic |
| --- | --- | --- | --- |
| ask_clarification | 241 (14.0%) | 49 (16.3%) | 42 (12.4%) |
| decline_not_covered | 458 (26.7%) | 88 (29.3%) | 100 (29.6%) |
| describe_table | 124 (7.2%) | 19 (6.3%) | 23 (6.8%) |
| make_chart | 166 (9.7%) | 20 (6.7%) | 28 (8.3%) |
| run_sql | 526 (30.6%) | 85 (28.3%) | 107 (31.7%) |
| search_catalog | 203 (11.8%) | 39 (13.0%) | 38 (11.2%) |

| `domain` | train | calibration | dev_synthetic |
| --- | --- | --- | --- |
| agriculture | 114 (6.6%) | 18 (6.0%) | 21 (6.2%) |
| health | 63 (3.7%) | 17 (5.7%) | 18 (5.3%) |
| labour | 627 (36.5%) | 116 (38.7%) | 125 (37.0%) |
| multiple | 108 (6.3%) | 26 (8.7%) | 23 (6.8%) |
| other | 88 (5.1%) | 10 (3.3%) | 16 (4.7%) |
| prices_economy | 71 (4.1%) | 14 (4.7%) | 22 (6.5%) |
| rainfall | 567 (33.0%) | 83 (27.7%) | 96 (28.4%) |
| unspecified | 80 (4.7%) | 16 (5.3%) | 17 (5.0%) |

## Text-to-SQL ground truth

- rows: 100
- dataset: NFHS-5 42, Mandi 34, NCRB 23, NCRB + NFHS-5 1
- difficulty: easy 60, medium 38, hard 2
- expected_action: answer 90, abstain 9, clarify 1
- category: filter 25, aggregation 17, filter_sort 16, top_k 9, quality_audit 7, derived_metric 6, temporal_coverage 3, window 2, self_join 2, partial_geography 2, sample_size 1, filter_aggregation 1, having 1, group_by 1, distinct 1, validation 1, missing_survey_round 1, incompatible_geography 1, missing_measure 1, measure_mismatch 1, unsupported_breakdown 1
- duplicate questions: 0

