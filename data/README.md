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
python scripts/download_raw.py       # NFHS-5 and Mandi into data/raw
python scripts/preprocess_data.py    # NFHS-5, Mandi and NCRB into data/processed
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
