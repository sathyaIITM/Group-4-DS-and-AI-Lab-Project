# Data

Raw downloads and cleaned tables are not tracked; reproduce them with the
scripts below. Row counts and SHA-256 of every prepared file are in
[MANIFEST.md](MANIFEST.md).

| Directory | Contents | Tracked |
| --- | --- | --- |
| `raw/` | Unmodified downloads from data.gov.in | No |
| `processed/` | Cleaned, versioned Parquet tables that DuckDB reads read-only | No |
| `sample/` | Small extracts committed so that tests and reviews run without downloads | Yes |
| `splits/kev/` | Routing splits v1 (train, calibration, dev-synthetic) | Yes |
| `ground_truths/` | Text-to-SQL reference pairs and their dev and test splits | Yes |

The test split is never used for training or tuning. Splits are separated by
question template, and leakage checks are run before use.

## Reproduction

From the repository root, with `DATA_GOV_IN_API_KEY` set:

```bash
python scripts/download_raw.py       # every API resource into data/raw (or name the files)
python scripts/run_pipeline.py       # all five tables into data/processed (see scripts/README.md)
python scripts/build_manifest.py     # compare hashes with MANIFEST.md
```

IMD and PLFS are fetched and converted with `analyst.data.ogd` and
`analyst.data.loaders` (see [sample/README.md](sample/README.md)). The Mandi
resource is a rolling daily snapshot, so a new download differs from the
Milestone 2 version of 29 October 2026.

## Raw files

| File | Title | Source |
| --- | --- | --- |
| `data/raw/datafile1.csv` | National Family Health Survey-5 (NFHS-5), India Districts Factsheet Data | data.gov.in resource `cf80173e-fece-439d-a0b1-6e9cb510593d`; https://www.data.gov.in/catalog/national-family-health-survey-5-nfhs-5-india-districts-factsheet-data-provisional |
| `data/raw/datafile2.csv` | Current daily price of various commodities from various markets (Mandi) | data.gov.in resource `9ef84268-d588-465a-a308-a864a43d0070`; https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi |
| `data/raw/datafile3.csv` | Year-wise Details of Crimes under IPC/BNS and SLL from 2022 to 2024 (NCRB, Crime in India 2024, Table 1.1(ii)) | catalogue download; https://www.data.gov.in/catalog/crime-india-cii-2024 |
| `data/raw/crop_production_district.csv` | District-wise, season-wise crop production statistics from 1997 (T1-1) | data.gov.in resource `35be999b-0208-4354-b557-f6ca9a5355de`; https://data.gov.in/resource/district-wise-season-wise-crop-production-statistics-1997 |
| `data/raw/cpi_all_india.csv` | All India Consumer Price Index (Rural/Urban) up to December 2023 (T1-2) | data.gov.in resource `2a6edbfb-b416-48db-9183-645be023f757`; https://www.data.gov.in/resource/all-india-consumer-price-index-ruralurban-upto-december-2023 |
| `data/raw/cpi_state.csv` | State Level Consumer Price Index (Rural/Urban) up to April 2023 (T1-3) | data.gov.in resource `09a191c9-3b2a-44ac-8d25-02475f83e723`; https://www.data.gov.in/resource/state-level-consumer-price-index-ruralurban-upto-april-2023 |
| `data/raw/nfhs5_state_factsheet.csv` | All India and State/UT-wise Factsheets of NFHS-5, 2019-2021 (T1-4) | data.gov.in resource `7c568619-b9b4-40bb-b563-68c28c27a6c1`; https://data.gov.in/resource/all-india-and-stateut-wise-factsheets-national-family-health-survey-nfhs-5-2019-2021 |
| `data/raw/imd_district_rainfall_normals.csv` | District Rainfall Normal (mm), monthly, seasonal and annual, 1951-2000 (T1-5) | data.gov.in resource `d0419b03-b41b-4226-b48b-0bc92bf139f8`; https://www.data.gov.in/resource/district-rainfall-normal-mm-monthly-seasonal-and-annual-data-period-1951-2000 |
| `data/raw/census2011_pca.csv` | Primary Census Abstract 2011, India (T1-6) | data.gov.in resource `0764657f-00ec-4c6b-9ece-2d7b8a7401fa`; https://www.data.gov.in/catalog/primary-census-abstract-2011-india-and-states |
| `data/raw/plfs_lfpr_urban_state.csv` | State/UT-wise LFPR, current weekly status, urban areas, PLFS 2023-24 (T1-7) | data.gov.in resource `67634139-cc72-4f90-a82f-d2b9b22488dc`; https://www.data.gov.in/resource/stateut-wise-details-labour-force-participation-rate-lfpr-according-current-weekly-0 |
| `data/raw/srs_imr_state.csv` | State/UTs-wise infant mortality rate (IMR), 2015-2019 (T2-1) | data.gov.in resource `d64574ca-33b9-4108-bd90-b3de1edd82a8`; https://www.data.gov.in/resource/stateuts-wise-details-infant-mortality-rate-imr-form-2015-2019 |
| `data/raw/gsdp_per_capita_state.csv` | State-wise per capita GSDP at current prices, 2019-20 to 2023-24 (T2-2) | data.gov.in resource `af17f25b-3bdf-4eeb-b3e3-b0fc93df16a7`; https://www.data.gov.in/resource/state-wise-details-capita-gross-state-domestic-product-gsdp-current-prices-2019-20-2023-24 |
| `data/raw/msp_crops.csv` | Commodity-wise minimum support prices (MSP), 2013-14 to 2024-25 (T2-3) | data.gov.in resource `82e89d31-2208-4be0-babd-2286a4d9110b`; https://www.data.gov.in/resource/commodity-wise-details-minimum-support-prices-msp-kharif-rabi-and-others-crops-2013-14 |

The source record of each T1 table (units, periods, place spellings, quirks) is in
[docs/specs/candidate_tables.md](../docs/specs/candidate_tables.md).
