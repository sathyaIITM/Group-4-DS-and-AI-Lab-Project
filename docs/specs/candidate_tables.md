# Candidate tables (T1)

Source record for the ten tables of the T1 task list (version 5, 5 November 2026) and for the
four files of the `data_discovery` branch. Each block follows the template of Section 8 of the
task list. Facts marked "from the file" were read from the raw download on 5 November 2026;
facts marked "from the task list" were checked by the T3 owner through the data.gov.in API on
the same day and are not yet confirmed from a download.

The five hand checks per table are recorded when the table is prepared (Section 5, step 7).

Canonical State/UT names are those of `configs/reference/states.csv` (commit `252dbda`, branch
`feature/t2-graph-skeleton`; not yet on `main`). "Alias needed" means that a spelling is not in
`configs/reference/place_aliases.csv`; an alias is added only after it is checked against the
official list.

## Status on 5 November 2026

| # | Table | Raw file (`data/raw/`) | Status |
| --- | --- | --- | --- |
| T1-1 | Crop production, district-wise | `crop_production_district.csv` | Not downloaded; due 11 November |
| T1-2 | All India CPI (Rural/Urban) up to December 2023 | `cpi_all_india.csv` | Downloaded; 393 rows as expected |
| T1-3 | State Level CPI (Rural/Urban) up to April 2023 | `cpi_state.csv` | Downloaded; 441 rows as expected; base-year rule pending |
| T1-4 | NFHS-5 State/UT factsheets | `nfhs5_state_factsheet.csv` | Downloaded; 110 rows (111 expected, see quirks) |
| T1-5 | District rainfall normals 1951-2000 | `imd_district_rainfall_normals.csv` | Downloaded; 640 rows (641 expected) |
| T1-6 | Primary Census Abstract 2011, India | `census2011_pca.csv` | Not downloaded; resource page not located (see block) |
| T1-7 | Urban LFPR (CWS), PLFS 2023-24 | `plfs_lfpr_urban_state.csv` | Downloaded; 37 rows as expected |
| T2-1 | State/UT infant mortality rate 2015-2019 | `srs_imr_state.csv` | Downloaded; 37 rows as expected |
| T2-2 | Per capita GSDP 2019-20 to 2023-24 | `gsdp_per_capita_state.csv` | Downloaded; 28 rows as expected |
| T2-3 | Minimum support prices 2013-14 to 2024-25 | `msp_crops.csv` | Downloaded; 29 rows as expected |

## Tier 1

### T1-1 District-wise, season-wise crop production statistics from 1997
- Resource id and page URL: `35be999b-0208-4354-b557-f6ca9a5355de`;
  https://data.gov.in/resource/district-wise-season-wise-crop-production-statistics-1997
- Publisher and licence: Ministry of Agriculture and Farmers Welfare (Directorate of Economics
  and Statistics); Government Open Data License - India
- Downloaded on: not yet downloaded
- Rows and columns (after download): 246,091 rows (from the task list); columns State, district,
  `Crop_Year`, season, crop, `Area`, `Production` (from the task list)
- Period covered and convention (calendar, fiscal, agricultural, survey year, month, quarter):
  from 1997; `Crop_Year` is the agricultural year (July-June); the catalogue says so
- Geography (India, State, district, sub-division) and spelling issues: district; spellings to
  be listed after download
- Units, and where the unit is stated: area in hectares; production in tonnes, except coconut
  (nuts), cotton (bales of 170 kg) and jute and mesta (bales of 180 kg); the unit per crop goes
  in the config
- Totals rows ("All India", "Total"): to be checked after download
- Known quirks (NA strings, footnote markers, years as columns, base year): mixed production
  units by crop (above); to be completed after download
- Join keys with the published tables (State name, district name, year): State and district
  name; agricultural year
- Five values checked by hand (value in our table = value on the publisher page): pending; one
  cotton and one coconut value are included, checked against the ministry's crop statistics
- Decision (from Section 3) and caveats for the catalogue: used (agriculture). Caveats: units
  differ by crop; agricultural year, not calendar year

### T1-2 All India Consumer Price Index (Rural/Urban), up to December 2023
- Resource id and page URL: `2a6edbfb-b416-48db-9183-645be023f757`;
  https://www.data.gov.in/resource/all-india-consumer-price-index-ruralurban-upto-december-2023
- Publisher and licence: Ministry of Statistics and Programme Implementation (National
  Statistics Office); Government Open Data License - India
- Downloaded on: 5 November 2026 (published file name `All_India_Index_Upto_Dec23.csv`)
- Rows and columns (after download): 393 rows, 30 columns: `Sector`, `Year`, `Month` and 27
  item groups from `Cereals and products` to `General index`
- Period covered and convention: month, January 2013 to December 2023; **April 2019 is absent**
  (no row for any sector), so 2019 has 33 rows instead of 36
- Geography and spelling issues: India only; `Sector` is `Rural`, `Urban` or `Rural+Urban`
- Units, and where the unit is stated: index, base 2012 = 100 (MoSPI CPI series; the base is
  not stated in the file)
- Totals rows: no "All India" row (the whole table is All India); `General index` is the
  all-groups column and `Rural+Urban` the combined sector
- Known quirks: item groups as columns (melt to rows); month misspelt `Marcrh` and one
  `November ` with a trailing space; `Housing` is `NA` in 122 rows (Rural: "not compiled", not
  zero) and `-` in 11 rows; 6 further `NA` in most other groups
- Join keys with the published tables: year and month; no geography join
- Five values checked by hand: pending
- Decision (from Section 3) and caveats for the catalogue: used (prices_economy). Caveats: index
  values, not prices; Rural `Housing` not compiled; April 2019 absent from the source

### T1-3 State Level Consumer Price Index (Rural/Urban), up to April 2023
- Resource id and page URL: `09a191c9-3b2a-44ac-8d25-02475f83e723`;
  https://www.data.gov.in/resource/state-level-consumer-price-index-ruralurban-upto-april-2023
- Publisher and licence: Ministry of Statistics and Programme Implementation (National
  Statistics Office); Government Open Data License - India
- Downloaded on: 5 November 2026 (published file name
  `Statewise_General_Index_july2019_20Aug2020_dec20_2_7.csv`)
- Rows and columns (after download): 441 rows, 39 columns: `Sector`, `Year`, `Name` (the month)
  and 36 States/UTs
- Period covered and convention: month, January 2011 to April 2023; **April 2019 is absent**
  (2019 has 33 rows); 2023 has January to April
- Geography and spelling issues: State/UT as columns. Names as the source spells them:
  Andhra Pradesh, Arunachal Pradesh, Assam, Bihar, Chattisgarh, Delhi, Goa, Gujarat, Haryana,
  Himachal Pradesh, Jharkhand, Karnataka, Kerala, Madhya Pradesh, Maharashtra, Manipur,
  Meghalaya, Mizoram, Nagaland, Orissa, Punjab, Rajasthan, Sikkim, Tamil Nadu, Telangana,
  Tripura, Uttar Pradesh, Uttarakhand, West Bengal, Andaman and Nicobar, Chandigarh, Dadra and
  Nagar Haveli, Daman and Diu, Jammu and Kashmir, Lakshadweep, Puducherry. Pre-2020 UT
  boundaries (Dadra and Nagar Haveli and Daman and Diu separate; no Ladakh)
- Units, and where the unit is stated: index (general index); base not stated in the file
- Totals rows: none (no All India column)
- Known quirks: States as columns (melt to rows); the month column is named `Name`; months
  misspelt `Auust`, `Macrh`, and `November `, `October `, `September ` with trailing spaces;
  `NA` in about 354 of 441 rows for Arunachal Pradesh (381), Bihar, Delhi, Nagaland, Rajasthan,
  Sikkim and Uttarakhand, and in 156 rows for Telangana; one `--` (Himachal Pradesh). **Base
  year:** January 2011 values are about 104, which fits base 2010 = 100, while recent values
  fit base 2012 = 100
- Join keys with the published tables: State name (aliases exist for Chattisgarh, Orissa,
  Andaman and Nicobar; Dadra and Nagar Haveli and Daman and Diu are historical names in
  `states.csv`); year and month
- Five values checked by hand: pending. Rule: compare five State values for 2015-2022 with
  MoSPI's CPI releases (base 2012 = 100)
- Decision (from Section 3) and caveats for the catalogue: used only if the base-year rule
  passes; then published from January 2013 and 2011-2012 dropped in the config; otherwise
  dropped and noted in the pull request

### T1-4 All India and State/UT-wise Factsheets of NFHS-5, 2019-2021
- Resource id and page URL: `7c568619-b9b4-40bb-b563-68c28c27a6c1`;
  https://data.gov.in/resource/all-india-and-stateut-wise-factsheets-national-family-health-survey-nfhs-5-2019-2021
- Publisher and licence: Ministry of Health and Family Welfare; International Institute for
  Population Sciences (IIPS); Government Open Data License - India
- Downloaded on: 5 November 2026
- Rows and columns (after download): 110 rows, 137 columns: `States/UTs`, `Area`, three
  sample sizes (households, women 15-49, men 15-54), 131 indicators, and one trailing column
  with an empty name and no values
- Period covered and convention: survey round NFHS-5, fieldwork 2019-2021; one round only
- Geography and spelling issues: India and 36 States/UTs, each by `Area` = `Total`, `Urban`,
  `Rural`. **West Bengal has no `Total` row** (only `Urban` and `Rural`), hence 110 rows, not
  111. Names as the source spells them: Andaman & Nicobar Islands, Andhra Pradesh, Arunachal
  Pradesh, Assam, Bihar, Chandigarh, Chhattisgarh, Dadra and Nagar Haveli & Daman and Diu, Goa,
  Gujarat, Haryana, Himachal Pradesh, India, Jammu & Kashmir, Jharkhand, Karnataka, Kerala,
  Ladakh, Lakshadweep, Madhya Pradesh, Maharastra, Manipur, Meghalaya, Mizoram, NCT of Delhi,
  Nagaland, Odisha, Puducherry, Punjab, Rajasthan, Sikkim, Tamil Nadu, Telangana, Tripura,
  Uttar Pradesh, Uttarakhand, West Bengal
- Units, and where the unit is stated: per indicator, in the column name: mostly percent
  (`(%)`); sex ratios per 1,000 males; adolescent fertility rate per 1,000 women; sample sizes
  as counts
- Totals rows: yes, `India` (Total, Urban, Rural)
- Known quirks: indicators as columns (melt to rows, keep `Area` as a column); 30 indicator
  names carry footnote digits (for example `source1 (%)`, `diet16, 17  (%)`), to be removed;
  `*` in 414 cells (NFHS convention: not shown, fewer than 25 unweighted cases); 375 values in
  parentheses such as `(69.2)` (NFHS convention: based on 25-49 unweighted cases); 3 blank
  cells; no `NA` string in this download; trailing spaces in 13,490 values; one column name
  with a leading space (` Sex ratio of the total population ...`)
- Join keys with the published tables: State name (aliases exist for all spellings above);
  joins `nfhs5_district_indicators` by indicator name after footnote digits are removed
- Five values checked by hand: pending
- Decision (from Section 3) and caveats for the catalogue: used (health); NFHS-5 values only.
  Caveats: survey estimates; `*` and parenthesised values flagged, not dropped; NFHS-5 IMR
  differs from SRS IMR (T2-1) by design; West Bengal Total absent in the source

### T1-5 District Rainfall Normal (mm), monthly, seasonal and annual, 1951-2000
- Resource id and page URL: `d0419b03-b41b-4226-b48b-0bc92bf139f8`;
  https://www.data.gov.in/resource/district-rainfall-normal-mm-monthly-seasonal-and-annual-data-period-1951-2000
- Publisher and licence: India Meteorological Department, Ministry of Earth Sciences;
  Government Open Data License - India
- Downloaded on: 5 November 2026
- Rows and columns (after download): 640 rows, 19 columns: `STATE/UT`, `DISTRICT`, `JAN` to
  `DEC`, `ANNUAL`, `JAN+FEB`, `MAM`, `JJAS`, `OND`
- Period covered and convention: long-term average over 1951-2000; one value per district and
  month or season; no year dimension
- Geography and spelling issues: district within 34 State/UT names, upper case, as the source
  spells them: ANDAMAN And NICOBAR ISLANDS, ANDHRA PRADESH, ARUNACHAL PRADESH, ASSAM, BIHAR,
  CHANDIGARH, CHATISGARH, DADAR NAGAR HAVELI, DAMAN AND DUI, DELHI, GOA, GUJARAT, HARYANA,
  HIMACHAL, JAMMU AND KASHMIR, JHARKHAND, KARNATAKA, KERALA, MADHYA PRADESH, MAHARASHTRA,
  MANIPUR, MEGHALAYA, MIZORAM, NAGALAND, ORISSA, PONDICHERRY, PUNJAB, RAJASTHAN, SIKKIM, TAMIL
  NADU, TRIPURA, UTTAR PRADESH, UTTARANCHAL, WEST BENGAL. No Telangana (pre-2014 Andhra
  Pradesh) and no Ladakh (district `LADAKH (LEH)` is under JAMMU AND KASHMIR); no Lakshadweep.
  636 distinct district names; four repeat across States (AURANGABAD, BIJAPUR, BILASPUR,
  HAMIRPUR), so the key is State plus district. 25 district names carry a parent-district code
  or are truncated (for example `TAWANG(W KAME`, `SONEPAT(RTK)`, `ANUPPUR(SHAHD`)
- Units, and where the unit is stated: millimetres, in the title
- Totals rows: none
- Known quirks: these are **normals**, not rainfall in a given year; no missing-value markers;
  season columns are sums of the months
- Join keys with the published tables: State name (aliases exist for ORISSA, PONDICHERRY,
  UTTARANCHAL; alias needed for CHATISGARH, HIMACHAL, DADAR NAGAR HAVELI, DAMAN AND DUI);
  district name; month. Districts do not join the IMD sub-division table
- Five values checked by hand: pending
- Decision (from Section 3) and caveats for the catalogue: used (rainfall). Caveats: long-term
  averages for 1951-2000, not observed rainfall; old district and State boundaries

### T1-6 Primary Census Abstract 2011, India
- Resource id and page URL: `0764657f-00ec-4c6b-9ece-2d7b8a7401fa`; resource page not located.
  Catalogue page: https://www.data.gov.in/catalog/primary-census-abstract-2011-india-and-states
  (on 5 November 2026 it listed one resource, `Primary Census Abstract 2011 - Jammu and
  Kashmir`; the portal search does not accept a resource id). Page link requested from the T3
  owner
- Publisher and licence: Registrar General and Census Commissioner, India (Ministry of Home
  Affairs); Government Open Data License - India
- Downloaded on: not yet downloaded
- Rows and columns (after download): 108 rows (from the task list)
- Period covered and convention: Census 2011 (reference date 1 March 2011)
- Geography and spelling issues: to be listed after download
- Units, and where the unit is stated: counts of households and persons
- Totals rows: to be checked after download
- Known quirks: to be completed after download; the catalogue page offers XLS, so a conversion
  to CSV may be needed
- Join keys with the published tables: State name
- Five values checked by hand: pending
- Decision (from Section 3) and caveats for the catalogue: used (supporting, population) for
  per-capita values and rates; the year 2011 stays visible in the catalogue entry

### T1-7 State/UT-wise LFPR, current weekly status (CWS), urban areas, PLFS 2023-24
- Resource id and page URL: `67634139-cc72-4f90-a82f-d2b9b22488dc`;
  https://www.data.gov.in/resource/stateut-wise-details-labour-force-participation-rate-lfpr-according-current-weekly-0
- Publisher and licence: Rajya Sabha answer, data of the Ministry of Statistics and Programme
  Implementation (PLFS); Government Open Data License - India
- Downloaded on: 5 November 2026
- Rows and columns (after download): 37 rows, 3 columns: `Sl. No.`, `State/UT`,
  `LFPR (in percent) according to CWS for Urban Areas`
- Period covered and convention: survey year July 2023-June 2024
- Geography and spelling issues: 36 States/UTs plus All India, spelt as in `states.csv`:
  Andaman and Nicobar Islands, Andhra Pradesh, Arunachal Pradesh, Assam, Bihar, Chandigarh,
  Chhattisgarh, Dadra and Nagar Haveli and Daman and Diu, Delhi, Goa, Gujarat, Haryana,
  Himachal Pradesh, Jammu and Kashmir, Jharkhand, Karnataka, Kerala, Ladakh, Lakshadweep,
  Madhya Pradesh, Maharashtra, Manipur, Meghalaya, Mizoram, Nagaland, Odisha, Puducherry,
  Punjab, Rajasthan, Sikkim, Tamil Nadu, Telangana, Tripura, Uttar Pradesh, Uttarakhand, West
  Bengal; All India
- Units, and where the unit is stated: percent, in the column name
- Totals rows: yes, `All India` (both `Sl. No.` and `State/UT` are `All India`; value 40)
- Known quirks: no missing values; age group not yet recorded (to be read from the Rajya Sabha
  answer linked from the resource page; if absent, "age group not stated in the source")
- Join keys with the published tables: State name; survey year
- Five values checked by hand: pending
- Decision (from Section 3) and caveats for the catalogue: used (labour). Caveats: urban only;
  CWS; survey year July 2023-June 2024; secondary source; not comparable with the published
  PLFS unemployment table (rural plus urban, usual status)

## Tier 2

### T2-1 State/UTs-wise infant mortality rate (IMR), 2015-2019
- Resource id and page URL: `d64574ca-33b9-4108-bd90-b3de1edd82a8` (file
  `RS_Session_256_AU_730_1.csv`);
  https://www.data.gov.in/resource/stateuts-wise-details-infant-mortality-rate-imr-form-2015-2019
- Publisher and licence: Office of the Registrar General of India, Sample Registration System,
  via Rajya Sabha Session 256, Unstarred Question 730; Government Open Data License - India
- Downloaded on: 3 November 2026 (data discovery); the copy in `data/raw/` is byte-identical
- Rows and columns (after download): 37 rows, 7 columns: `Sl. No.`, `National/ State/ UT`,
  `Infant Mortality Rate (per 1000 live births) - 2015` to `- 2019`
- Period covered and convention: calendar years 2015-2019; smaller States/UTs are three-year
  averages labelled with the last year
- Geography and spelling issues: All India and 36 areas: Andaman and Nicobar Islands, Andhra
  Pradesh, Arunachal Pradesh, Assam, Bihar, Chandigarh, Chhattisgarh, Dadra and Nagar Haveli,
  Daman and Diu, Delhi, Goa, Gujarat, Haryana, Himachal Pradesh, Jammu and Kashmir Including
  Ladakh, Jharkhand, Karnataka, Kerala, Lakshadweep, Madhya Pradesh, Maharashtra, Manipur,
  Meghalaya, Mizoram, Nagaland, Odisha, Puducherry, Punjab, Rajasthan, Sikkim, Tamil Nadu,
  Telangana, Tripura, Uttar Pradesh, Uttarakhand, West Bengal
- Units, and where the unit is stated: deaths per 1,000 live births, in the column names
- Totals rows: yes, `All India` (first row; `Sl. No.` is also `All India`)
- Known quirks: years as columns (melt to rows); no missing values; `Jammu and Kashmir
  Including Ladakh` is its own area (SRS publishes them combined), not an alias
- Join keys with the published tables: State name (Dadra and Nagar Haveli and Daman and Diu are
  historical names in `states.csv`); year
- Five values checked by hand: pending
- Decision (from Section 3) and caveats for the catalogue: used (health). Caveats: secondary
  source; three-year averages for smaller areas; SRS IMR differs from NFHS-5 IMR (T1-4) by design

### T2-2 State-wise per capita GSDP at current prices, 2019-20 to 2023-24
- Resource id and page URL: `af17f25b-3bdf-4eeb-b3e3-b0fc93df16a7`;
  https://www.data.gov.in/resource/state-wise-details-capita-gross-state-domestic-product-gsdp-current-prices-2019-20-2023-24
- Publisher and licence: Rajya Sabha answer (Session 265, according to the resource page);
  Government Open Data License - India
- Downloaded on: 5 November 2026
- Rows and columns (after download): 28 rows, 7 columns: `Sl. No.`, `State`,
  `Per Capita GSDP - 2019-2020`, `- 2020-2021`, `- 2021-22`, `- 2022-23`, `- 2023-24`
- Period covered and convention: fiscal years (April-March) 2019-20 to 2023-24
- Geography and spelling issues: 28 States, no UTs: Andhra Pradesh, Arunachal Pradesh, Assam,
  Bihar, Chhatisgarh, Goa, Gujarat, Haryana, Himachal Pradesh, Jharkhand, Karnataka, Kerala,
  Madhya Pradesh, Maharashtra, Manipur, Meghalaya, Mizoram, Nagaland, Odisha, Punjab,
  Rajasthan, Sikkim, Tamil Nadu, Telangana, Tripura, Uttar Pradesh, Uttarakhand, West Bengal
- Units, and where the unit is stated: rupees (from the task list); the file does not state the
  unit
- Totals rows: none
- Known quirks: fiscal years as columns (melt to rows), written two ways (`2019-2020` and
  `2021-22`); `NA` for 2023-24 in six States (Arunachal Pradesh, Goa, Gujarat, Manipur,
  Mizoram, Nagaland)
- Join keys with the published tables: State name (alias needed for `Chhatisgarh`); fiscal year
- Five values checked by hand: pending
- Decision (from Section 3) and caveats for the catalogue: used (prices_economy). Caveats:
  secondary source; current prices; no UTs; 2023-24 incomplete

### T2-3 Commodity-wise minimum support prices (MSP), 2013-14 to 2024-25
- Resource id and page URL: `82e89d31-2208-4be0-babd-2286a4d9110b`;
  https://www.data.gov.in/resource/commodity-wise-details-minimum-support-prices-msp-kharif-rabi-and-others-crops-2013-14
- Publisher and licence: Rajya Sabha answer (Session 266, Unstarred Question 510, 29 November
  2024, according to the resource page), data of the Department of Agriculture and Farmers
  Welfare; Government Open Data License - India
- Downloaded on: 5 November 2026
- Rows and columns (after download): 29 rows, 16 columns: `Sl. No.`, `Commodity`, `Category`,
  `Variety`, `2013-14` to `2024-25`
- Period covered and convention: marketing years 2013-14 to 2024-25; Copra and De-husked
  Coconut by calendar year (stated in their names)
- Geography and spelling issues: India only. Commodities (24): Bajra, Barley, Copra (Calender
  Year), Cotton, De-husked Coconut (Calender Year), Gram, Groundnut, Jowar, Jute, Maize, Masur
  (Lentil), Moong, Nigerseed, Paddy, Ragi, Rapeseed And Mustard, Safflower, Sesamum, Soyabean,
  Sugarcane, Sunflower Seed, Tur (Arhar), Urad, Wheat. Categories: Kharif Crops, Rabi Crops,
  Other Crops. Varieties: Ball, Black, Common, Grade A, Hybrid, Long Staple, Maldandi, Medium
  Staple, Milling, Yellow, `NA`
- Units, and where the unit is stated: rupees per quintal (from the task list); the file does
  not state the unit
- Totals rows: none
- Known quirks: years as columns (melt to rows); `Variety` is `NA` (no variety) in 19 rows;
  Soyabean Black is `NA` from 2014-15 to 2024-25 ("no longer fixed", not missing); Sugarcane is
  the fair and remunerative price, not an MSP; `Calender` misspelt in the source
- Join keys with the published tables: commodity name (Mandi prices) and year; no geography
- Five values checked by hand: pending; checked against the MSP statement on desagri.gov.in
- Decision (from Section 3) and caveats for the catalogue: used (agriculture). Caveats:
  secondary source; Sugarcane is FRP; Copra and coconut by calendar year

## Files of the `data_discovery` branch

The four files were committed to the repository root on the `data_discovery` branch on
3 November 2026 (commit `fe79839`). A local copy is kept outside the repository. The branch is
deleted without merging.

### `RS_Session_256_AU_730_1.csv` (infant mortality)
- Resource id and page URL: `d64574ca-33b9-4108-bd90-b3de1edd82a8`; see T2-1
- Publisher and licence: see T2-1
- Downloaded on: 3 November 2026
- Rows and columns (after download): 37 rows, 7 columns (1,403 bytes)
- Period covered and convention, geography, units, totals, quirks, join keys: see T2-1
- Five values checked by hand: see T2-1
- Decision (from Section 3) and caveats for the catalogue: **used as T2-1** (D2); the file in
  `data/raw/srs_imr_state.csv` is byte-identical

### `labour-force-participation-rate-lfpr.csv` (quarterly LFPR)
- Resource id and page URL: India Data Portal copy of the PLFS quarterly series; no
  data.gov.in resource
- Publisher and licence: India Data Portal (republisher); not a government host
- Downloaded on: before 3 November 2026
- Rows and columns (after download): 5,175 rows (313,901 bytes)
- Period covered and convention: quarters; the 2018 rows carry shifted gender labels
- Geography and spelling issues: State
- Units, and where the unit is stated: percent
- Totals rows: not recorded
- Known quirks: shifted gender labels in 2018; no machine-readable government copy exists
- Join keys with the published tables: not applicable
- Five values checked by hand: not applicable
- Decision (from Section 3) and caveats for the catalogue: **not used** (D1, D3); replaced by
  T1-7. If the quarterly series is re-sourced from a government host, it starts at
  January-March 2019

### `daily-rainfall-at-state-level.csv` (daily rainfall)
- Resource id and page URL: India Data Portal copy; no data.gov.in resource
- Publisher and licence: India Data Portal (republisher); not a government host
- Downloaded on: before 3 November 2026
- Rows and columns (after download): 202,234 rows (12.9 MB)
- Period covered and convention: day
- Geography and spelling issues: State; pre-2020 UT boundaries
- Units, and where the unit is stated: millimetres
- Totals rows: not recorded
- Known quirks: two UTs with no observations, three with no normals, 60 further missing days per
  State, an undefined `rfs` column
- Join keys with the published tables: not applicable
- Five values checked by hand: not applicable
- Decision (from Section 3) and caveats for the catalogue: **not used** (D1, D4); rainfall is
  covered by T1-5 and the published IMD sub-division table

### `RF_SUB_1901-2021.csv` (sub-division rainfall)
- Resource id and page URL: not recorded
- Publisher and licence: not stated which series is a revision of the published IMD table
- Downloaded on: before 3 November 2026
- Rows and columns (after download): 227,091 bytes; four months only
- Period covered and convention: calendar years 1901-2021
- Geography and spelling issues: IMD sub-division
- Units, and where the unit is stated: millimetres
- Totals rows: not recorded
- Known quirks: differs from the published IMD table in about 2,000 of 2,790 shared
  sub-division-years
- Join keys with the published tables: sub-division and year (not to be used)
- Five values checked by hand: not applicable
- Decision (from Section 3) and caveats for the catalogue: **not used** (D2). Its 2018-2021 years
  must not be added to the existing IMD table
