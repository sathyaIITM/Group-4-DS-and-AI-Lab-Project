# Candidate tables (T1)

Source record for the ten tables of the T1 task list (version 5, 5 November 2026) and for the
four files of the `data_discovery` branch. Each block follows the template of Section 8 of the
task list. Facts marked "from the file" were read from the raw download on 5 November 2026;
facts marked "from the task list" were checked by the T3 owner through the data.gov.in API on
the same day and are not yet confirmed from a download.

The five hand checks per table are recorded when the table is prepared (Section 5, step 7).

Each downloaded table also has a **Column descriptions** list: every column of the raw file, in
file order, with its name exactly as the source spells it, its type and what it holds. The
descriptions were read from the files in `data/raw/` on 11 November 2026. "Text" is a label,
"integer" and "decimal" are numbers, and the missing-value markers each column uses are named.
Tables not yet downloaded (T1-1, T1-6) and the `data_discovery` files have no column list.

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

#### Column descriptions (`cpi_all_india.csv`, 30 columns)

Columns 4-30 are Consumer Price Index values for an item group, base 2012 = 100, given to one
decimal (observed range about 85 to 295). `NA` means the source has no value. The groups follow
the MoSPI CPI (2012 series) structure: columns 4-15 are the subgroups of `Food and beverages`,
columns 18-19 the subgroups of `Clothing and footwear`, and columns 23-29 the subgroups of
`Miscellaneous`.

| # | Column | Type | Description |
| --- | --- | --- | --- |
| 1 | `Sector` | Text | Area the index covers: `Rural`, `Urban`, or `Rural+Urban` (combined) |
| 2 | `Year` | Integer | Calendar year, 2013 to 2023 |
| 3 | `Month` | Text | Month name, January to December (spelling errors listed under quirks) |
| 4 | `Cereals and products` | Decimal | Index for rice, wheat, other cereals and their products (flour, etc.) |
| 5 | `Meat and fish` | Decimal | Index for meat, poultry and fish |
| 6 | `Egg` | Decimal | Index for eggs |
| 7 | `Milk and products` | Decimal | Index for milk, curd, ghee and other dairy products |
| 8 | `Oils and fats` | Decimal | Index for edible oils, vanaspati and other fats |
| 9 | `Fruits` | Decimal | Index for fresh and dry fruits |
| 10 | `Vegetables` | Decimal | Index for vegetables, including potato, onion and tomato |
| 11 | `Pulses and products` | Decimal | Index for pulses (dal) and gram products |
| 12 | `Sugar and Confectionery` | Decimal | Index for sugar, jaggery, honey and confectionery |
| 13 | `Spices` | Decimal | Index for spices, salt and condiments |
| 14 | `Non-alcoholic beverages` | Decimal | Index for tea, coffee, soft drinks and similar |
| 15 | `Prepared meals, snacks, sweets etc.` | Decimal | Index for cooked meals, snacks and sweets bought ready to eat |
| 16 | `Food and beverages` | Decimal | Group index for all of columns 4-15 together |
| 17 | `Pan, tobacco and intoxicants` | Decimal | Group index for pan, tobacco products and intoxicants |
| 18 | `Clothing` | Decimal | Index for clothing, tailoring and clothing materials |
| 19 | `Footwear` | Decimal | Index for footwear |
| 20 | `Clothing and footwear` | Decimal | Group index for columns 18-19 together |
| 21 | `Housing` | Decimal | Group index for house rent. Compiled for urban areas only, so Rural rows are `NA`; `-` in 11 rows |
| 22 | `Fuel and light` | Decimal | Group index for cooking fuel, electricity and lighting |
| 23 | `Household goods and services` | Decimal | Index for furniture, utensils, appliances and domestic services |
| 24 | `Health` | Decimal | Index for medicines, doctor's fees and other medical expenses |
| 25 | `Transport and communication` | Decimal | Index for vehicles, fuel for vehicles, fares, phone and postal charges |
| 26 | `Recreation and amusement` | Decimal | Index for entertainment, cinema, sports goods and similar |
| 27 | `Education` | Decimal | Index for school and college fees, books and stationery |
| 28 | `Personal care and effects` | Decimal | Index for toiletries, cosmetics, jewellery and other personal items |
| 29 | `Miscellaneous` | Decimal | Group index for columns 23-28 together |
| 30 | `General index` | Decimal | All-groups CPI: the headline consumer price index for the sector and month |

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

#### Column descriptions (`cpi_state.csv`, 39 columns)

| # | Column | Type | Description |
| --- | --- | --- | --- |
| 1 | `Sector` | Text | Area the index covers: `Rural`, `Urban`, or `Rural+Urban` (combined) |
| 2 | `Year` | Integer | Calendar year, 2011 to 2023 |
| 3 | `Name` | Text | Month name, January to December. The column holds the month although it is called `Name` (spelling errors listed under quirks) |
| 4-39 | `Andhra Pradesh` ... `Puducherry` (36 columns, one per State/UT, names listed above) | Decimal | General (all-groups) CPI for that State/UT in the given sector and month, mostly 100 to 200. `NA` where no index was compiled for the State/UT; `--` once (Himachal Pradesh) |

Note from the file: the row `Urban, 2021, November` does not hold index values. Its 36 values
run from 0.01 (Lakshadweep) to 18.86 (Maharashtra) and add up to 100.01, so they look like the
States' weights in the urban index, not the November 2021 index. The row must be set to missing
(or replaced from MoSPI's release) when the table is prepared.

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

#### Column descriptions (`nfhs5_state_factsheet.csv`, 137 columns)

Columns 1-5 describe the row (area and sample sizes). Columns 6-136 are the 131 NFHS-5
indicators, one value per area row. In the raw file the indicator columns are stored as text,
because the values carry trailing spaces, `*` (not shown: fewer than 25 unweighted cases),
parentheses such as `(69.2)` (based on 25-49 unweighted cases) and a few blanks; once cleaned
they are decimal numbers. Unless the Unit column says otherwise, a value is a percentage of the
group named in the description, and questions about births refer to births in the five years
before the survey. A footnote number in a column name refers to the NFHS-5 factsheet notes and
is removed when the table is prepared; the descriptions name it. Names are shown trimmed;
leading and trailing spaces in the source are mentioned in the description.

| # | Column (as in the file) | Unit | Description |
| --- | --- | --- | --- |
| 1 | `States/UTs` | - | Area name: `India` or a State/UT, as the source spells it |
| 2 | `Area` | - | Part of the area the row covers: `Total`, `Urban` or `Rural` |
| 3 | `Number of Households surveyed` | count | Number of households surveyed (sample size) |
| 4 | `Number of Women age 15-49 years interviewed` | count | Number of women aged 15-49 interviewed (sample size) |
| 5 | `Number of Men age 15-54 years interviewed` | count | Number of men aged 15-54 interviewed (sample size) |
| 6 | `Female population age 6 years and above who ever attended school (%)` | % | Share of females aged 6 and above who have ever attended school |
| 7 | `Population below age 15 years (%)` | % | Share of the household population younger than 15 |
| 8 | `Sex ratio of the total population (females per 1,000 males)` | females per 1,000 males | Sex ratio of the whole household population. The column name starts with a space |
| 9 | `Sex ratio at birth for children born in the last five years (females per 1,000 males)` | females per 1,000 males | Sex ratio at birth, for children born in the five years before the survey |
| 10 | `Children under age 5 years whose birth was registered with the civil authority (%)` | % | Share of children under 5 whose birth was registered with the civil authority |
| 11 | `Deaths in the last 3 years registered with the civil authority (%)` | % | Share of deaths in the household in the last 3 years that were registered with the civil authority |
| 12 | `Population living in households with electricity (%)` | % | Share of the population living in households with electricity |
| 13 | `Population living in households with an improved drinking-water source1 (%)` | % | Share of the population living in households with an improved drinking-water source (footnote 1) |
| 14 | `Population living in households that use an improved sanitation facility2 (%)` | % | Share of the population living in households that use an improved sanitation facility (footnote 2) |
| 15 | `Households using clean fuel for cooking3 (%)` | % | Share of households using clean fuel (for example LPG or electricity) for cooking (footnote 3) |
| 16 | `Households using iodized salt (%)` | % | Share of households using iodized salt |
| 17 | `Households with any usual member covered under a health insurance/financing scheme (%)` | % | Share of households where at least one usual member is covered by a health insurance or financing scheme |
| 18 | `Children age 5 years who attended pre-primary school during the school year 2019-20 (%)` | % | Share of children aged 5 who attended pre-primary school in the 2019-20 school year |
| 19 | `Women (age 15-49) who are literate4 (%)` | % | Share of women aged 15-49 who are literate (footnote 4) |
| 20 | `Men (age 15-49) who are literate4 (%)` | % | Share of men aged 15-49 who are literate (footnote 4) |
| 21 | `Women (age 15-49)  with 10 or more years of schooling (%)` | % | Share of women aged 15-49 with 10 or more years of schooling |
| 22 | `Men (age 15-49)  with 10 or more years of schooling (%)` | % | Share of men aged 15-49 with 10 or more years of schooling |
| 23 | `Women (age 15-49)  who have ever used the internet (%)` | % | Share of women aged 15-49 who have ever used the internet |
| 24 | `Men (age 15-49)  who have ever used the internet (%)` | % | Share of men aged 15-49 who have ever used the internet |
| 25 | `Women age 20-24 years married before age 18 years (%)` | % | Share of women aged 20-24 who married before age 18 (child marriage) |
| 26 | `Men age 25-29 years married before age 21 years (%)` | % | Share of men aged 25-29 who married before age 21 |
| 27 | `Total Fertility Rate (number of children per woman)` | children per woman | Total fertility rate: the number of children a woman would have at current age-specific birth rates |
| 28 | `Women age 15-19 years who were already mothers or pregnant at the time of the survey (%)` | % | Share of women aged 15-19 who were already mothers or pregnant at the time of the survey |
| 29 | `Adolescent fertility rate for women age 15-19 years5` | births per 1,000 women | Adolescent fertility rate: births per year per 1,000 women aged 15-19 (footnote 5) |
| 30 | `Neonatal mortality rate (per 1000 live births)` | per 1,000 live births | Neonatal mortality rate: deaths in the first 28 days of life |
| 31 | `Infant mortality rate (per 1000 live births)` | per 1,000 live births | Infant mortality rate: deaths before age 1 |
| 32 | `Under-five mortality rate (per 1000 live births)` | per 1,000 live births | Under-five mortality rate: deaths before age 5 |
| 33 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - Any method6 (%)` | % | Share of currently married women aged 15-49 using any family planning method (footnote 6) |
| 34 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - Any modern method6 (%)` | % | Share of currently married women aged 15-49 using any modern method (footnote 6) |
| 35 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - Female sterilization (%)` | % | Share of currently married women aged 15-49 relying on female sterilisation |
| 36 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - Male sterilization (%)` | % | Share of currently married women aged 15-49 relying on male sterilisation |
| 37 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - IUD/PPIUD (%)` | % | Share of currently married women aged 15-49 using an IUD or post-partum IUD |
| 38 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - Pill (%)` | % | Share of currently married women aged 15-49 using the pill |
| 39 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - Condom (%)` | % | Share of currently married women aged 15-49 using condoms |
| 40 | `Current Use of Family Planning Methods (Currently Married Women Age 15-49  years) - Injectables (%)` | % | Share of currently married women aged 15-49 using injectables |
| 41 | `Total Unmet need for Family Planning (Currently Married Women Age 15-49  years)7 (%)` | % | Total unmet need: currently married women aged 15-49 who want to stop or delay childbearing but use no method (footnote 7) |
| 42 | `Unmet need for spacing (Currently Married Women Age 15-49  years)7 (%)` | % | Unmet need for spacing: as column 41, for women who want to delay the next birth (footnote 7) |
| 43 | `Health worker ever talked to female non-users about family planning (%)` | % | Share of women not using family planning whom a health worker ever talked to about it |
| 44 | `Current users ever told about side effects of current method of family planning8 (%)` | % | Share of current users of a method who were ever told about its side effects (footnote 8) |
| 45 | `Mothers who had an antenatal check-up in the first trimester  (for last birth in the 5 years before the survey) (%)` | % | Share of mothers who had an antenatal check-up in the first trimester (last birth in the 5 years before the survey) |
| 46 | `Mothers who had at least 4 antenatal care visits  (for last birth in the 5 years before the survey) (%)` | % | Share of mothers who had at least 4 antenatal care visits (last birth in the 5 years before the survey) |
| 47 | `Mothers whose last birth was protected against neonatal tetanus (for last birth in the 5 years before the survey)9 (%)` | % | Share of mothers whose last birth was protected against neonatal tetanus (footnote 9) |
| 48 | `Mothers who consumed iron folic acid for 100 days or more when they were pregnant (for last birth in the 5 years before the survey) (%)` | % | Share of mothers who took iron folic acid for 100 days or more during pregnancy |
| 49 | `Mothers who consumed iron folic acid for 180 days or more when they were pregnant (for last birth in the 5 years before the survey} (%)` | % | Share of mothers who took iron folic acid for 180 days or more during pregnancy. The column name ends `survey}` (curly brace) |
| 50 | `Registered pregnancies for which the mother received a Mother and Child Protection (MCP) card (for last birth in the 5 years before the survey) (%)` | % | Share of registered pregnancies for which the mother received a Mother and Child Protection (MCP) card |
| 51 | `Mothers who received postnatal care from a doctor/nurse/LHV/ANM/midwife/other health personnel within 2 days of delivery (for last birth in the 5 years before the survey) (%)` | % | Share of mothers who received postnatal care from a health worker within 2 days of delivery |
| 52 | `Average out-of-pocket expenditure per delivery in a public health facility (for last birth in the 5 years before the survey) (Rs.)` | rupees | Average out-of-pocket expenditure per delivery in a public health facility (last birth in the 5 years before the survey) |
| 53 | `Children born at home who were taken to a health facility for a check-up within 24 hours of birth (for last birth in the 5 years before the survey} (%)` | % | Share of children born at home who were taken to a health facility for a check-up within 24 hours of birth. The column name ends `survey}` |
| 54 | `Children who received postnatal care from a doctor/nurse/LHV/ANM/midwife/ other health personnel within 2 days of delivery (for last birth in the 5 years before the survey) (%)` | % | Share of children who received postnatal care from a health worker within 2 days of delivery |
| 55 | `Institutional births (in the 5 years before the survey) (%)` | % | Share of births in the 5 years before the survey that took place in a health facility |
| 56 | `Institutional births in public facility (in the 5 years before the survey) (%)` | % | Share of births in the 5 years before the survey that took place in a public health facility |
| 57 | `Home births that were conducted by skilled health personnel  (in the 5 years before the survey)10 (%)` | % | Share of home births conducted by skilled health personnel (footnote 10) |
| 58 | `Births attended by skilled health personnel (in the 5 years before the survey)10 (%)` | % | Share of births attended by skilled health personnel (footnote 10) |
| 59 | `Births delivered by caesarean section (in the 5 years before the survey) (%)` | % | Share of births delivered by caesarean section |
| 60 | `Births in a private health facility that were delivered by caesarean section (in the 5 years before the survey) (%)` | % | Share of births in private health facilities delivered by caesarean section |
| 61 | `Births in a public health facility that were delivered by caesarean section (in the 5 years before the survey) (%)` | % | Share of births in public health facilities delivered by caesarean section |
| 62 | `Children age 12-23 months fully vaccinated based on information from either vaccination card or mother's recall11 (%)` | % | Share of children aged 12-23 months fully vaccinated, from the vaccination card or the mother's recall (footnote 11) |
| 63 | `Children age 12-23 months fully vaccinated based on information from vaccination card only12 (%)` | % | Share of children aged 12-23 months fully vaccinated, from the vaccination card only (footnote 12) |
| 64 | `Children age 12-23 months who have received BCG (%)` | % | Share of children aged 12-23 months who received BCG |
| 65 | `Children age 12-23 months who have received 3 doses of polio vaccine13 (%)` | % | Share of children aged 12-23 months who received 3 doses of polio vaccine (footnote 13) |
| 66 | `Children age 12-23 months who have received 3 doses of penta or DPT vaccine (%)` | % | Share of children aged 12-23 months who received 3 doses of penta or DPT vaccine |
| 67 | `Children age 12-23 months who have received the first dose of measles-containing vaccine (MCV) (%)` | % | Share of children aged 12-23 months who received the first dose of measles-containing vaccine |
| 68 | `Children age 24-35 months who have received a second dose of measles-containing vaccine (MCV) (%)` | % | Share of children aged 24-35 months who received the second dose of measles-containing vaccine |
| 69 | `Children age 12-23 months who have received 3 doses of rotavirus vaccine14 (%)` | % | Share of children aged 12-23 months who received 3 doses of rotavirus vaccine (footnote 14) |
| 70 | `Children age 12-23 months who have received 3 doses of penta or hepatitis B vaccine (%)` | % | Share of children aged 12-23 months who received 3 doses of penta or hepatitis B vaccine |
| 71 | `Children age 9-35 months who received a vitamin A dose in the last 6 months (%)` | % | Share of children aged 9-35 months who received a vitamin A dose in the last 6 months |
| 72 | `Children age 12-23 months who received most of their vaccinations in a public health facility (%)` | % | Share of children aged 12-23 months who received most vaccinations in a public health facility |
| 73 | `Children age 12-23 months who received most of their vaccinations in a private health facility (%)` | % | Share of children aged 12-23 months who received most vaccinations in a private health facility |
| 74 | `Prevalence of diarrhoea in the 2 weeks preceding the survey (Children under age 5 years) (%)` | % | Share of children under 5 who had diarrhoea in the 2 weeks before the survey. Trailing space in the name |
| 75 | `Children with diarrhoea in the 2 weeks preceding the survey who received oral rehydration salts (ORS) (Children under age 5 years) (%)` | % | Share of those children (column 74) who received oral rehydration salts (ORS). Trailing space in the name |
| 76 | `Children with diarrhoea in the 2 weeks preceding the survey who received zinc (Children under age 5 years) (%)` | % | Share of those children (column 74) who received zinc. Trailing space in the name |
| 77 | `Children swith diarrhoea in the 2 weeks preceding the survey taken to a health facility or health provider (Children under age 5 years) (%)` | % | Share of those children (column 74) taken to a health facility or provider. Name misspelt `swith`; trailing space |
| 78 | `Children Prevalence of symptoms of acute respiratory infection (ARI) in the 2 weeks preceding the survey (Children under age 5 years) (%)` | % | Share of children under 5 with symptoms of acute respiratory infection (ARI) in the 2 weeks before the survey. Trailing space |
| 79 | `Children with fever or symptoms of ARI in the 2 weeks preceding the survey taken to a health facility or health provider (Children under age 5 years) (%)` | % | Share of children under 5 with fever or ARI symptoms taken to a health facility or provider. Two trailing spaces |
| 80 | `Children under age 3 years breastfed within one hour of birth15 (%)` | % | Share of children under 3 breastfed within one hour of birth (footnote 15) |
| 81 | `Children under age 6 months exclusively breastfed16 (%)` | % | Share of children under 6 months exclusively breastfed (footnote 16) |
| 82 | `Children age 6-8 months receiving solid or semi-solid food and breastmilk16 (%)` | % | Share of children aged 6-8 months receiving solid or semi-solid food and breastmilk (footnote 16) |
| 83 | `Breastfeeding children age 6-23 months receiving an adequate diet16, 17  (%)` | % | Share of breastfeeding children aged 6-23 months receiving an adequate diet (footnotes 16, 17) |
| 84 | `Non-breastfeeding children age 6-23 months receiving an adequate diet16, 17 (%)` | % | Share of non-breastfeeding children aged 6-23 months receiving an adequate diet (footnotes 16, 17) |
| 85 | `Total children age 6-23 months receiving an adequate diet16, 17  (%)` | % | Share of all children aged 6-23 months receiving an adequate diet (footnotes 16, 17) |
| 86 | `Children under 5 years who are stunted (height-for-age)18 (%)` | % | Share of children under 5 who are stunted (too short for their age) (footnote 18) |
| 87 | `Children under 5 years who are wasted (weight-for-height)18 (%)` | % | Share of children under 5 who are wasted (too thin for their height) (footnote 18) |
| 88 | `Children under 5 years who are severely wasted (weight-for-height)19 (%)` | % | Share of children under 5 who are severely wasted (footnote 19) |
| 89 | `Children under 5 years who are underweight (weight-for-age)18 (%)` | % | Share of children under 5 who are underweight (too light for their age) (footnote 18) |
| 90 | `Children under 5 years who are overweight (weight-for-height)20 (%)` | % | Share of children under 5 who are overweight for their height (footnote 20) |
| 91 | `Women (age 15-49 years) whose Body Mass Index (BMI) is below normal (BMI <18.5 kg/m2)21 (%)` | % | Share of women aged 15-49 with BMI below 18.5 kg/m2 (underweight) (footnote 21) |
| 92 | `Men (age 15-49 years) whose Body Mass Index (BMI) is below normal (BMI <18.5 kg/m2) (%)` | % | Share of men aged 15-49 with BMI below 18.5 kg/m2 (underweight) |
| 93 | `Women (age 15-49 years) who are overweight or obese (BMI ≥25.0 kg/m2)21 (%)` | % | Share of women aged 15-49 who are overweight or obese (BMI 25.0 kg/m2 or more) (footnote 21) |
| 94 | `Men (age 15-49 years) who are overweight or obese (BMI ≥25.0 kg/m2) (%)` | % | Share of men aged 15-49 who are overweight or obese (BMI 25.0 kg/m2 or more) |
| 95 | `Women (age 15-49 years) who have high risk waist-to-hip ratio (≥0.85) (%)` | % | Share of women aged 15-49 with a high-risk waist-to-hip ratio (0.85 or more) |
| 96 | `Men (age 15-49 years) who have high risk waist-to-hip ratio (≥0.90) (%)` | % | Share of men aged 15-49 with a high-risk waist-to-hip ratio (0.90 or more) |
| 97 | `Children age 6-59 months who are anaemic (<11.0 g/dl)22 (%)` | % | Share of children aged 6-59 months who are anaemic (haemoglobin below 11.0 g/dl) (footnote 22) |
| 98 | `Non-pregnant women age 15-49 years who are anaemic (<12.0 g/dl)22 (%)` | % | Share of non-pregnant women aged 15-49 who are anaemic (below 12.0 g/dl) (footnote 22) |
| 99 | `Pregnant women age 15-49 years who are anaemic (<11.0 g/dl)22 (%)` | % | Share of pregnant women aged 15-49 who are anaemic (below 11.0 g/dl) (footnote 22) |
| 100 | `All women age 15-49 years who are anaemic22 (%)` | % | Share of all women aged 15-49 who are anaemic (footnote 22) |
| 101 | `All women age 15-19 years who are anaemic22 (%)` | % | Share of all women aged 15-19 who are anaemic (footnote 22). Trailing space in the name |
| 102 | `Men age 15-49 years who are anaemic (<13.0 g/dl)22 (%)` | % | Share of men aged 15-49 who are anaemic (below 13.0 g/dl) (footnote 22) |
| 103 | `Men age 15-19 years who are anaemic (<13.0 g/dl)22 (%)` | % | Share of men aged 15-19 who are anaemic (below 13.0 g/dl) (footnote 22) |
| 104 | `Women  age 15 years and above with high (141-160 mg/dl) Blood sugar level23 (%)` | % | Share of women aged 15 and above with high blood sugar (141-160 mg/dl) (footnote 23) |
| 105 | `Women age 15 years and above wih very high (>160 mg/dl) Blood sugar level23 (%)` | % | Share of women aged 15 and above with very high blood sugar (above 160 mg/dl) (footnote 23). `wih` misspelt in the source, also in columns 106-115 |
| 106 | `Women age 15 years and above wih high or very high (>140 mg/dl) Blood sugar level or taking medicine to control blood sugar level23 (%)` | % | Share of women aged 15 and above with high or very high blood sugar (above 140 mg/dl) or taking medicine for it (footnote 23) |
| 107 | `Men age 15 years and above wih high (141-160 mg/dl) Blood sugar level23 (%)` | % | Share of men aged 15 and above with high blood sugar (141-160 mg/dl) (footnote 23) |
| 108 | `Men (age 15 years and above wih  very high (>160 mg/dl) Blood sugar level23 (%)` | % | Share of men aged 15 and above with very high blood sugar (above 160 mg/dl) (footnote 23) |
| 109 | `Men age 15 years and above wih high or very high (>140 mg/dl) Blood sugar level  or taking medicine to control blood sugar level23 (%)` | % | Share of men aged 15 and above with high or very high blood sugar (above 140 mg/dl) or taking medicine for it (footnote 23) |
| 110 | `Women age 15 years and above wih Mildly elevated blood pressure (Systolic 140-159 mm of Hg and/or Diastolic 90-99 mm of Hg) (%)` | % | Share of women aged 15 and above with mildly elevated blood pressure (systolic 140-159 and/or diastolic 90-99 mm Hg) |
| 111 | `Women age 15 years and above wih Moderately or severely elevated blood pressure (Systolic ≥160 mm of Hg and/or Diastolic ≥100 mm of Hg) (%)` | % | Share of women aged 15 and above with moderately or severely elevated blood pressure (systolic 160+ and/or diastolic 100+ mm Hg) |
| 112 | `Women age 15 years and above wih Elevated blood pressure (Systolic ≥140 mm of Hg and/or Diastolic ≥90 mm of Hg) or taking medicine to control blood pressure (%)` | % | Share of women aged 15 and above with elevated blood pressure (systolic 140+ and/or diastolic 90+ mm Hg) or taking medicine for it |
| 113 | `Men age 15 years and above wih Mildly elevated blood pressure (Systolic 140-159 mm of Hg and/or Diastolic 90-99 mm of Hg) (%)` | % | As column 110, for men |
| 114 | `Men age 15 years and above wih Moderately or severely elevated blood pressure (Systolic ≥160 mm of Hg and/or Diastolic ≥100 mm of Hg) (%)` | % | As column 111, for men |
| 115 | `Men age 15 years and above wih Elevated blood pressure (Systolic ≥140 mm of Hg and/or Diastolic ≥90 mm of Hg) or taking medicine to control blood pressure (%)` | % | As column 112, for men |
| 116 | `Women (age 30-49 years) Ever undergone a screening test for cervical cancer (%)` | % | Share of women aged 30-49 who have ever had a screening test for cervical cancer |
| 117 | `Women (age 30-49 years) Ever undergone a breast examination for breast cancer (%)` | % | Share of women aged 30-49 who have ever had a breast examination for breast cancer |
| 118 | `Women (age 30-49 years) Ever undergone an oral cavity examination for oral cancer (%)` | % | Share of women aged 30-49 who have ever had an oral cavity examination for oral cancer |
| 119 | `Men (age 30-49 years)Ever undergone an oral cavity examination for oral cancer (%)` | % | Share of men aged 30-49 who have ever had an oral cavity examination for oral cancer |
| 120 | `Women (age 15-49 years) who have comprehensive knowledge24 of HIV/AIDS (%)` | % | Share of women aged 15-49 with comprehensive knowledge of HIV/AIDS (footnote 24) |
| 121 | `Men (age 15-49 years) who have comprehensive knowledge24 of HIV/AIDS (%)` | % | Share of men aged 15-49 with comprehensive knowledge of HIV/AIDS (footnote 24) |
| 122 | `Women (age 15-49 years) who know that consistent condom use can reduce the chance of getting HIV/AIDS (%)` | % | Share of women aged 15-49 who know that consistent condom use can reduce the chance of HIV/AIDS |
| 123 | `Men (age 15-49 years) who know that consistent condom use can reduce the chance of getting HIV/AIDS (%)` | % | Share of men aged 15-49 who know that consistent condom use can reduce the chance of HIV/AIDS |
| 124 | `Currently married women (age 15-49 years) who usually participate in three household decisions25 (%)` | % | Share of currently married women aged 15-49 who usually take part in three household decisions (footnote 25) |
| 125 | `Women (age 15-49 years) who worked in the last 12 months and were paid in cash (%)` | % | Share of women aged 15-49 who worked in the last 12 months and were paid in cash |
| 126 | `Women (age 15-49 years) owning a house and/or land (alone or jointly with others) (%)` | % | Share of women aged 15-49 who own a house and/or land, alone or jointly |
| 127 | `Women (age 15-49 years) having a bank or savings account that they themselves use (%)` | % | Share of women aged 15-49 with a bank or savings account that they use themselves |
| 128 | `Women (age 15-49 years) having a mobile phone that they themselves use (%)` | % | Share of women aged 15-49 with a mobile phone that they use themselves |
| 129 | `Women age 15-24 years who use hygienic methods of protection during their menstrual period26 (%)` | % | Share of women aged 15-24 who use hygienic methods of protection during menstruation (footnote 26) |
| 130 | `Ever-married women age 18-49 years who have ever experienced spousal violence27 (%)` | % | Share of ever-married women aged 18-49 who have ever experienced spousal violence (footnote 27) |
| 131 | `Ever-married women age 18-49 years who have experienced physical violence during any pregnancy (%)` | % | Share of ever-married women aged 18-49 who experienced physical violence during any pregnancy |
| 132 | `Young women age 18-29 years who experienced sexual violence by age 18 (%)` | % | Share of young women aged 18-29 who experienced sexual violence by age 18 |
| 133 | `Women age 15 years and above who use any kind of tobacco (%)` | % | Share of women aged 15 and above who use any kind of tobacco |
| 134 | `Men age 15 years and above who use any kind of tobacco (%)` | % | Share of men aged 15 and above who use any kind of tobacco |
| 135 | `Women age 15 years and above who consume alcohol (%)` | % | Share of women aged 15 and above who drink alcohol |
| 136 | `Men age 15 years and above who consume alcohol (%)` | % | Share of men aged 15 and above who drink alcohol |
| 137 | (no name) | - | Trailing column with no name and no values; to be dropped |

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

#### Column descriptions (`imd_district_rainfall_normals.csv`, 19 columns)

Columns 3-19 are rainfall normals in millimetres, given to one decimal: the average rainfall of
that month or season over 1951-2000. No value is missing. Checked in the file: `ANNUAL` and the
four season columns equal the sum of their months (to within 1 mm) in all 640 rows.

| # | Column | Type | Description |
| --- | --- | --- | --- |
| 1 | `STATE/UT` | Text | State/UT name, upper case, as the source spells it (pre-2014 boundaries; list above) |
| 2 | `DISTRICT` | Text | District name, upper case; some names carry a parent-district code or are cut short (see above). Unique only together with `STATE/UT` |
| 3 | `JAN` | Decimal | Normal rainfall in January (mm) |
| 4 | `FEB` | Decimal | Normal rainfall in February (mm) |
| 5 | `MAR` | Decimal | Normal rainfall in March (mm) |
| 6 | `APR` | Decimal | Normal rainfall in April (mm) |
| 7 | `MAY` | Decimal | Normal rainfall in May (mm) |
| 8 | `JUN` | Decimal | Normal rainfall in June (mm) |
| 9 | `JUL` | Decimal | Normal rainfall in July (mm) |
| 10 | `AUG` | Decimal | Normal rainfall in August (mm) |
| 11 | `SEP` | Decimal | Normal rainfall in September (mm) |
| 12 | `OCT` | Decimal | Normal rainfall in October (mm) |
| 13 | `NOV` | Decimal | Normal rainfall in November (mm) |
| 14 | `DEC` | Decimal | Normal rainfall in December (mm) |
| 15 | `ANNUAL` | Decimal | Normal rainfall for the whole year, January to December (mm) |
| 16 | `JAN+FEB` | Decimal | Winter season: January plus February (mm) |
| 17 | `MAM` | Decimal | Pre-monsoon season: March, April and May (mm) |
| 18 | `JJAS` | Decimal | South-west monsoon season: June to September (mm) |
| 19 | `OND` | Decimal | Post-monsoon (north-east monsoon) season: October, November and December (mm) |

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

#### Column descriptions (`plfs_lfpr_urban_state.csv`, 3 columns)

| # | Column | Type | Description |
| --- | --- | --- | --- |
| 1 | `Sl. No.` | Integer (text in one row) | Serial number of the row in the Rajya Sabha answer, 1 to 36; `All India` in the totals row. Not a data value |
| 2 | `State/UT` | Text | State/UT name, or `All India` for the national row |
| 3 | `LFPR (in percent) according to CWS for Urban Areas` | Decimal | Labour force participation rate in urban areas, current weekly status: the percentage of the population that was working or seeking work in the reference week. One decimal; range 30.5 to 50.6; All India 40 |

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

#### Column descriptions (`srs_imr_state.csv`, 7 columns)

| # | Column | Type | Description |
| --- | --- | --- | --- |
| 1 | `Sl. No.` | Integer (text in one row) | Serial number of the row in the Rajya Sabha answer, 1 to 36; `All India` in the first (totals) row. Not a data value |
| 2 | `National/ State/ UT` | Text | `All India` or a State/UT name (list above) |
| 3 | `Infant Mortality Rate (per 1000 live births) - 2015` | Integer | Infant mortality rate in 2015: deaths of infants under one year per 1,000 live births (SRS). Whole numbers |
| 4 | `Infant Mortality Rate (per 1000 live births) - 2016` | Integer | As column 3, for 2016 |
| 5 | `Infant Mortality Rate (per 1000 live births) - 2017` | Integer | As column 3, for 2017 |
| 6 | `Infant Mortality Rate (per 1000 live births) - 2018` | Integer | As column 3, for 2018 |
| 7 | `Infant Mortality Rate (per 1000 live births) - 2019` | Integer | As column 3, for 2019 |

For smaller States/UTs a year's value is the three-year average ending in that year (see
above). Range over all years: 3 to 50; All India falls from 37 (2015) to 30 (2019).

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

#### Column descriptions (`gsdp_per_capita_state.csv`, 7 columns)

| # | Column | Type | Description |
| --- | --- | --- | --- |
| 1 | `Sl. No.` | Integer | Serial number of the row in the Rajya Sabha answer, 1 to 28. Not a data value |
| 2 | `State` | Text | State name (28 States, no UTs; list above) |
| 3 | `Per Capita GSDP - 2019-2020` | Integer | Gross State Domestic Product per person at current prices for fiscal year 2019-20 (April 2019-March 2020), in rupees |
| 4 | `Per Capita GSDP - 2020-2021` | Integer | As column 3, for 2020-21 |
| 5 | `Per Capita GSDP - 2021-22` | Integer | As column 3, for 2021-22 |
| 6 | `Per Capita GSDP - 2022-23` | Integer | As column 3, for 2022-23 |
| 7 | `Per Capita GSDP - 2023-24` | Integer | As column 3, for 2023-24; `NA` for six States (not yet released) |

Values are whole rupees, from about 46,000 to 707,000. "Current prices" means the prices of
each year, with no adjustment for inflation.

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

#### Column descriptions (`msp_crops.csv`, 16 columns)

| # | Column | Type | Description |
| --- | --- | --- | --- |
| 1 | `Sl. No.` | Integer | Serial number of the row in the Rajya Sabha answer, 1 to 29. Not a data value |
| 2 | `Commodity` | Text | Crop the price is fixed for (24 commodities, list above); Copra and De-husked Coconut are marked "(Calender Year)" |
| 3 | `Category` | Text | Crop season group: `Kharif Crops` (monsoon-sown), `Rabi Crops` (winter-sown) or `Other Crops` |
| 4 | `Variety` | Text | Variety or grade of the commodity (for example `Common` and `Grade A` paddy, `Long Staple` cotton); `NA` when the commodity has one price only |
| 5 | `2013-14` | Integer | Minimum support price for marketing year 2013-14, in rupees per quintal (100 kg); for Sugarcane the fair and remunerative price |
| 6 | `2014-15` | Integer | As column 5, for 2014-15 |
| 7 | `2015-16` | Integer | As column 5, for 2015-16 |
| 8 | `2016-17` | Integer | As column 5, for 2016-17 |
| 9 | `2017-18` | Integer | As column 5, for 2017-18 |
| 10 | `2018-19` | Integer | As column 5, for 2018-19 |
| 11 | `2019-20` | Integer | As column 5, for 2019-20 |
| 12 | `2020-21` | Integer | As column 5, for 2020-21 |
| 13 | `2021-22` | Integer | As column 5, for 2021-22 |
| 14 | `2022-23` | Integer | As column 5, for 2022-23 |
| 15 | `2023-24` | Integer | As column 5, for 2023-24 |
| 16 | `2024-25` | Integer | As column 5, for 2024-25 |

Values are whole rupees per quintal, from 210 (Sugarcane, 2013-14) to 12,000. In the year
columns `NA` appears only for Soyabean Black from 2014-15 on (no longer fixed, not missing).

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
