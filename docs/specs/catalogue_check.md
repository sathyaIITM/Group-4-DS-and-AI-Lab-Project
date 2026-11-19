# Catalogue check

Produced by `scripts/check_catalogue.py --samples 5 --seed 0` from `data/processed/catalogue.json` (contract 1.1).

Traced values matching the raw file: 70 of 70.

## Reviewer checklist (T1 brief, Section 5.1)

Reviewed on 17 November 2026 against the tables built from the data.gov.in API copies produced by `scripts/download_raw.py` (canonical raw files, decision of 17 November 2026). The table of facts and the traced values below were produced by this script; the judgements are recorded here.

| Item | Result |
| --- | --- |
| `title` and `caveats` understandable without the source page | Yes for every table. NFHS-5 State: the caveat that West Bengal has no Total figure was removed, because the API copy has one (131 values). |
| `domain` follows the rules | Yes. Crop production and MSP are `agriculture`; CPI, GSDP and Mandi are `prices_economy`; the NCRB tables are `other`. |
| Period types and conventions match the publisher | Yes. PLFS unemployment July-June (start month 7); urban LFPR one survey round, July 2023 to June 2024; GSDP fiscal years (start month 4); MSP agricultural years (start month 7); CPI calendar months, base 2012 = 100; NCRB and SRS calendar years; NFHS-5 one survey round, 2019-2021; IMD district normals the 1951-2000 average. |
| `indicator_units` correct | Yes after two corrections. In the API export, five NFHS-5 State headers and three NFHS-5 district headers end "... before the survey)" without "(%)"; a unit rule now gives them `percent` (they were `unknown`). Crop production units are per crop; MSP rupees per quintal; CPI an index with base 2012 = 100. |
| `geo_levels` and `has_total_rows` correct; total-row names listed | Yes. Total rows: "All India" (PLFS unemployment, urban LFPR, SRS IMR), "India" (NFHS-5 State), "Total All India" (NCRB State). NCRB State subtotals "Total State (S)" and "Total UT (S)" are removed on reading (`read.drop_rows`) and reported. |
| `coverage_start` and `coverage_end` match the data | Yes (table below). |
| Flag counts explained | See the next section. |
| `python scripts/run_pipeline.py --verify` passes | Yes: "release verified" (17 November 2026). |
| Five values per table traced to the publisher's file | Yes: 70 of 70 published values match their raw cell (section "Values traced to the raw file"). |

### Flag counts

- **NFHS-5 State, 357 `low_sample_estimate`**: the API export writes the factsheet's bracketed low-sample estimates "(29.5)" as "-29.5". The registered rule `nfhs5_minus_as_low_sample`, already used for the district table, now applies to the State table too. Without it the values were published as negative and flagged `out_of_range`.
- **NFHS-5 State, 414 `suppressed` and 3 `missing_in_source`**: "*" (fewer than 25 cases, not shown by NFHS) and "NA" in the API export.
- **NFHS-5 district, 4,884 `low_sample_estimate` and 4,132 `suppressed`**: as above, for the district factsheets.
- **Mandi, 13 `implausible`**: 7 prices below INR 1 per quintal (minimum INR 0.01) and 6 rows whose maximum exceeds ten times the modal price; kept and flagged, as in Milestone 2.
- **Crop production, 3,730 `missing_in_source`**: empty production or area cells in the source. Years absent for a district and crop are not rows; the engine reports them as period gaps (crops are not grown every year in every district).
- **CPI All India, 250 `missing_in_source`**: cells empty in the source. In addition, **April 2019 is absent for all 81 series** (27 item groups x 3 sectors): 131 of the 132 months from January 2013 to December 2023 are published. The month is absent in T1's earlier copy as well (same value count, 10,611). Absent periods are not rows, so they carry no flag; the engine reports them as a period gap.
- **GSDP, 6 `missing_in_source`**: 2023-24 for six States, as the caveat states.
- **MSP 11, PLFS unemployment 4, IMD sub-divisions 134 `missing_in_source`**: empty cells in the source.

### Differences from T1's build

- **NFHS-5 State**: 13 of 131 indicator ids change because the API headers differ from T1's file ("≥" written ">=", "}" typos written ")", "(%)" absent from five headers). The mapping is recorded for the retrieval content and the `e2e_v1` set. The table has 14,541 values (T1's build: 14,410), the difference being the West Bengal Total row.
- **IMD district rainfall normals**: 641 districts and 10,897 values (T1's build: 640 and 10,880). The additional district could not be identified from T1's approved profile, which records counts only.

## Facts per table

| Table | Domain | Periods | Start month | Geography | Total rows | Coverage | Units | Flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cpi_all_india` | prices_economy | month | - | national | no | 2013-01-01 to 2023-12-31 | index_2012_100 | missing_in_source 250, reported 10,361 |
| `crop_production_district` | agriculture | survey_year | 7 | district | no | 1997-07-01 to 2016-06-30 | bale_170kg, bale_180kg, hectare, mixed_nuts_or_tonne (+1) | missing_in_source 3,730, reported 488,452 |
| `gsdp_per_capita_state` | prices_economy | survey_year | 4 | state | no | 2019-04-01 to 2024-03-31 | INR | missing_in_source 6, reported 134 |
| `imd_district_rainfall_normals` | rainfall | survey_round | - | district | no | 1951-01-01 to 2000-12-31 | mm | reported 10,897 |
| `imd_subdivision_monthly_rainfall` | rainfall | calendar_year, month, season | - | subdivision | no | 1901-01-01 to 2017-12-31 | mm | missing_in_source 134, reported 71,062 |
| `mandi_daily_prices` | prices_economy | date | - | market | no | 2026-10-29 to 2026-10-29 | INR_per_quintal | implausible 13, reported 49,166 |
| `msp_crops` | agriculture | survey_year | 7 | national | no | 2013-07-01 to 2025-06-30 | INR_per_quintal | missing_in_source 11, reported 337 |
| `ncrb_annual_crime_statistics` | other | calendar_year | - | national | no | 2022-01-01 to 2024-12-31 | count, lakh, per_100000_population, percent | reported 24 |
| `ncrb_violent_crimes_state` | other | calendar_year | - | national, state | yes | 2021-01-01 to 2023-12-31 | count | reported 111 |
| `nfhs5_district_indicators` | health | survey_round | - | district | no | 2019-01-01 to 2021-12-31 | INR, per_1000_males, percent | low_sample_estimate 4,884, reported 64,512, suppressed 4,132 |
| `nfhs5_state_factsheet` | health | survey_round | - | national, state | yes | 2019-01-01 to 2021-12-31 | INR, births_per_1000_women, children_per_woman, per_1000_live_births (+2) | low_sample_estimate 357, missing_in_source 3, reported 13,767, suppressed 414 |
| `plfs_lfpr_urban_state` | labour | survey_round | - | national, state | yes | 2023-07-01 to 2024-06-30 | percent | reported 37 |
| `plfs_state_ur_usual_status` | labour | survey_year | 7 | national, state | yes | 2017-07-01 to 2022-06-30 | percent | missing_in_source 4, reported 186 |
| `srs_imr_state` | health | calendar_year | - | national, state | yes | 2015-01-01 to 2019-12-31 | per_1000_live_births | reported 185 |

## Values traced to the raw file

### `cpi_all_india`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| India | 2017-06 | `cpi_recreation_and_amusement` | 129.8 | 129.8 | yes |
| India | 2022-07 | `cpi_housing` | 167.8 | 167.8 | yes |
| India | 2020-11 | `cpi_personal_care_and_effects` | 156.2 | 156.2 | yes |
| India | 2013-03 | `cpi_general_index` | 106.0 | 106 | yes |
| India | 2014-07 | `cpi_vegetables` | 172.4 | 172.4 | yes |

### `crop_production_district`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| BULANDSHAHR | 2004-05 | `crop_area` | 8456.0 | 8456 | yes |
| KIPHIRE | 2012-13 | `crop_production` | 570.0 | 570 | yes |
| ASHOKNAGAR | 2006-07 | `crop_production` | 45262.0 | 45262 | yes |
| GHAZIABAD | 1998-99 | `crop_area` | 1684.0 | 1684 | yes |
| GOLAGHAT | 2000-01 | `crop_area` | 9.0 | 9 | yes |

### `gsdp_per_capita_state`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Arunachal Pradesh | 2022-23 | `gsdp_per_capita_current` | 225770.0 | 225770 | yes |
| Goa | 2022-23 | `gsdp_per_capita_current` | 567344.0 | 567344 | yes |
| Meghalaya | 2021-22 | `gsdp_per_capita_current` | 120678.0 | 120678 | yes |
| Nagaland | 2020-21 | `gsdp_per_capita_current` | 136093.0 | 136093 | yes |
| Chhattisgarh | 2022-23 | `gsdp_per_capita_current` | 154609.0 | 154609 | yes |

### `imd_district_rainfall_normals`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| ADILABAD | 1951-2000 | `rainfall_normal_jan` | 7.5 | 7.5 | yes |
| MAHOBA | 1951-2000 | `rainfall_normal_jf` | 28.0 | 28 | yes |
| SOUTH SIKKIM | 1951-2000 | `rainfall_normal_jun` | 464.6 | 464.6 | yes |
| SAHUJI MAHARA | 1951-2000 | `rainfall_normal_mam` | 20.2 | 20.2 | yes |
| NORTH DINAJPUR | 1951-2000 | `rainfall_normal_jun` | 316.0 | 316 | yes |

### `imd_subdivision_monthly_rainfall`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Saurashtra & Kutch | 1975-MAM | `rainfall_mm` | 0.0 | 0 | yes |
| Punjab | 1999-12 | `rainfall_mm` | 0.2 | 0.2 | yes |
| Uttarakhand | 2016-07 | `rainfall_mm` | 508.4 | 508.4 | yes |
| East Madhya Pradesh | 1903-04 | `rainfall_mm` | 0.9 | 0.9 | yes |
| Vidarbha | 1972-06 | `rainfall_mm` | 139.8 | 139.8 | yes |

### `mandi_daily_prices`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Neemuch APMC | 2026-10-29 | `min_price_inr_per_quintal` | 3010.0 | 3010 | yes |
| Bina APMC | 2026-10-29 | `max_price_inr_per_quintal` | 7650.0 | 7650 | yes |
| Mannargudi II(Uzhavar Sandhai ) | 2026-10-29 | `min_price_inr_per_quintal` | 4400.0 | 4400 | yes |
| Mayabander Vegetable Market | 2026-10-29 | `max_price_inr_per_quintal` | 7500.0 | 7500 | yes |
| Katpadi (Uzhavar Sandhai ) | 2026-10-29 | `max_price_inr_per_quintal` | 9000.0 | 9000 | yes |

### `msp_crops`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| India | 2014-15 | `msp` | 1360.0 | 1360 | yes |
| India | 2018-19 | `msp` | 1950.0 | 1950 | yes |
| India | 2013-14 | `msp` | 1250.0 | 1250 | yes |
| India | 2018-19 | `msp` | 5877.0 | 5877 | yes |
| India | 2016-17 | `msp` | 3950.0 | 3950 | yes |

### `ncrb_annual_crime_statistics`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| India | 2023 | `sll_crime_count` | 2478467.0 | 2478467 | yes |
| India | 2022 | `total_crime_rate` | 422.2 | 422.2 | yes |
| India | 2024 | `population_lakhs` | 14049.1 | 14049.1 | yes |
| India | 2022 | `ipc_bns_crime_rate` | 258.1 | 258.1 | yes |
| India | 2024 | `sll_crime_rate` | 166.6 | 166.6 | yes |

### `ncrb_violent_crimes_state`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Ladakh | 2022 | `violent_crime_count` | 33.0 | 33 | yes |
| Assam | 2021 | `violent_crime_count` | 26933.0 | 26933 | yes |
| Jammu and Kashmir | 2023 | `violent_crime_count` | 2446.0 | 2446 | yes |
| Chhattisgarh | 2023 | `violent_crime_count` | 8602.0 | 8602 | yes |
| Ladakh | 2021 | `violent_crime_count` | 23.0 | 23 | yes |

### `nfhs5_district_indicators`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Puducherry | 2019-2021 | `nfhs5_children_under_age_3_years_breastfed_within_one_hour_of_birth15_f0a1ad8f` | 52.5 | 52.5 | yes |
| North & Middle Andaman | 2019-2021 | `nfhs5_children_age_5_years_who_attended_pre_primary_school_during_the_school_year_2019_20_c1f628d3` | 30.1 | -30.1 | yes |
| Bhind | 2019-2021 | `nfhs5_women_age_30_49_years_ever_undergone_an_oral_cavity_examination_for_oral_cancer_965821d8` | 0.6 | 0.6 | yes |
| Gajapati | 2019-2021 | `nfhs5_women_age_15_49_years_who_have_high_risk_waist_to_hip_ratio_0_85_0f7803d1` | 68.6 | 68.6 | yes |
| Tinsukia | 2019-2021 | `nfhs5_births_in_a_private_health_facility_that_were_delivered_by_caesarean_section_in_the_5_year_3c1c02ff` | 58.4 | -58.4 | yes |

### `nfhs5_state_factsheet`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Haryana | 2019-2021 | `nfhs5_state_men_age_15_49_years_who_know_that_consistent_condom_use_can_reduce_the_chance_of_getting_h_aa92ddf5` | 86.8 | 86.8 | yes |
| Tripura | 2019-2021 | `nfhs5_state_children_under_age_3_years_breastfed_within_one_hour_of_birth15_f0a1ad8f` | 36.4 | 36.4 | yes |
| India | 2019-2021 | `nfhs5_state_women_age_30_49_years_ever_undergone_a_breast_examination_for_breast_cancer_a2ca88f5` | 1.2 | 1.2 | yes |
| Chandigarh | 2019-2021 | `nfhs5_state_children_age_24_35_months_who_have_received_a_second_dose_of_measles_containing_vaccine_mc_d7030515` | 15.0 | -15 | yes |
| Uttar Pradesh | 2019-2021 | `nfhs5_state_children_age_9_35_months_who_received_a_vitamin_a_dose_in_the_last_6_months_103f671d` | 73.1 | 73.1 | yes |

### `plfs_lfpr_urban_state`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Kerala | 2023-24 | `lfpr_cws_urban` | 39.8 | 39.8 | yes |
| Maharashtra | 2023-24 | `lfpr_cws_urban` | 42.7 | 42.7 | yes |
| Meghalaya | 2023-24 | `lfpr_cws_urban` | 45.0 | 45 | yes |
| Andaman and Nicobar Islands | 2023-24 | `lfpr_cws_urban` | 46.1 | 46.1 | yes |
| Bihar | 2023-24 | `lfpr_cws_urban` | 30.5 | 30.5 | yes |

### `plfs_state_ur_usual_status`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Odisha | 2017-18 | `ur_usual_ps_ss` | 7.1 | 7.1 | yes |
| Manipur | 2019-20 | `ur_usual_ps_ss` | 9.5 | 9.5 | yes |
| Karnataka | 2019-20 | `ur_usual_ps_ss` | 4.2 | 4.2 | yes |
| Bihar | 2017-18 | `ur_usual_ps_ss` | 7.0 | 7 | yes |
| Bihar | 2021-22 | `ur_usual_ps_ss` | 5.9 | 5.9 | yes |

### `srs_imr_state`

| Place | Period | Indicator | Published | Raw cell | Match |
| --- | --- | --- | --- | --- | --- |
| Kerala | 2019 | `imr_srs` | 6.0 | 6 | yes |
| Arunachal Pradesh | 2016 | `imr_srs` | 36.0 | 36 | yes |
| Puducherry | 2015 | `imr_srs` | 11.0 | 11 | yes |
| Meghalaya | 2019 | `imr_srs` | 33.0 | 33 | yes |
| Uttar Pradesh | 2018 | `imr_srs` | 43.0 | 43 | yes |

