# Routing data v2: coverage of the training and validation splits

Produced by `python -m analyst.models.kev_report coverage`. 'Named' counts records whose
template names the table; 'top-1' counts records whose retrieved catalogue ranks it
first. Paraphrased and teacher-labelled records name no template table.

| Table | Domain | train.v2.jsonl named / top-1 | calibration.v2.jsonl named / top-1 | dev_synthetic.v2.jsonl named / top-1 |
| --- | --- | --- | --- | --- |
| `plfs_state_ur_usual_status` | labour | 244 / 498 | 28 / 68 | 37 / 61 |
| `imd_subdivision_monthly_rainfall` | rainfall | 202 / 293 | 11 / 25 | 20 / 27 |
| `ncrb_violent_crimes_state` | other | 43 / 40 | 6 / 3 | 29 / 11 |
| `ncrb_annual_crime_statistics` | other | 27 / 29 | 8 / 9 | 7 / 11 |
| `cpi_all_india` | prices_economy | 27 / 106 | 6 / 18 | 2 / 22 |
| `gsdp_per_capita_state` | prices_economy | 45 / 111 | 12 / 21 | 4 / 29 |
| `msp_crops` | agriculture | 28 / 112 | 1 / 20 | 12 / 25 |
| `mandi_daily_prices` | prices_economy | 19 / 27 | 19 / 14 | 10 / 6 |
| `srs_imr_state` | health | 41 / 91 | 4 / 22 | 4 / 27 |
| `plfs_lfpr_urban_state` | labour | 37 / 132 | 5 / 17 | 11 / 32 |
| `imd_district_rainfall_normals` | rainfall | 25 / 75 | 3 / 11 | 14 / 16 |
| `nfhs5_district_indicators` | health | 41 / 65 | 11 / 18 | 18 / 11 |
| `nfhs5_state_factsheet` | health | 27 / 134 | 15 / 39 | 13 / 38 |
| `crop_production_district` | agriculture | 38 / 163 | 8 / 37 | 8 / 39 |

| Domain label | train.v2.jsonl | calibration.v2.jsonl | dev_synthetic.v2.jsonl |
| --- | --- | --- | --- |
| labour | 597 (31.8%) | 93 (28.9%) | 102 (28.7%) |
| rainfall | 473 (25.2%) | 63 (19.6%) | 72 (20.3%) |
| other | 171 (9.1%) | 27 (8.4%) | 48 (13.5%) |
| health | 166 (8.8%) | 43 (13.4%) | 45 (12.7%) |
| prices_economy | 149 (7.9%) | 42 (13.0%) | 26 (7.3%) |
| agriculture | 125 (6.7%) | 21 (6.5%) | 28 (7.9%) |
| unspecified | 102 (5.4%) | 21 (6.5%) | 13 (3.7%) |
| multiple | 93 (5.0%) | 12 (3.7%) | 21 (5.9%) |
