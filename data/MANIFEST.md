# Data manifest

Produced by `scripts/build_manifest.py` on 2026-11-03. Recompute after regenerating any file; a changed hash means a changed version.

## Raw downloads (`data/raw`, not tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/raw/datafile1.csv` | 707 | 109 | 356,689 | `de06b72f241fa9734676677a15941b93b890009b1c0f88be655b07e8a853a689` |
| `data/raw/datafile2.csv` | 16,393 | 10 | 1,577,826 | `6f5bb19d0814247222160ea24df581c982b74ff4608a2486cca5a9d62ad1b73d` |
| `data/raw/datafile3.csv` | 3 | 9 | 415 | `c04a05dd3359fe8a024d73126f6abd51a7fc1c3802d68bc527490816f2205512` |
| `data/raw/imd_subdivision_monthly_rainfall.csv` | 4,188 | 19 | 441,180 | `f655f42e672001c09fbd68ca14041f7299c76883d7aa9167400a1f963948bbad` |
| `data/raw/plfs_state_ur_usual_status_2017_22.csv` | 38 | 7 | 1,340 | `1c1b78de7d20ff7d75e40701fc3b940f0804c80032ba25bf79a78d1fb030b1a6` |

## Processed tables (`data/processed`, not tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/processed/dim_period.parquet` | 47,482 | 6 | 433,722 | `d57333207a4129b786b06391ca5fee0292db098a8ced5aa17affcdef47cfacfe` |
| `data/processed/imd_subdivision_monthly_rainfall.parquet` | 4,188 | 21 | 264,309 | `aebf88a7faa13d4ce8052316d0a9b6764220c71b70d947556963b0fb029925e8` |
| `data/processed/mandi_daily_prices.parquet` | 16,393 | 23 | 191,450 | `f7890ca7e7a25a029a5632cc39c613430a35acb0150e55bd1f72a7011edbe371` |
| `data/processed/ncrb_annual_crime_statistics.parquet` | 3 | 23 | 14,227 | `1787a31d588c0d13979f4c1300fbef1f519d298e0eb9fbcabaf9a5cc94d2b912` |
| `data/processed/nfhs5_district_indicators.parquet` | 73,528 | 21 | 312,155 | `b8d7a983d3276f51f7abe30bc79220043fae3940717ce27a0839ee1e04129072` |
| `data/processed/obs_imd_subdivision_monthly_rainfall.parquet` | 71,196 | 27 | 732,536 | `274fe27bb2575a43fad6fec6115895ee0d882f43502d47c9072fbbb7055d3ec3` |
| `data/processed/obs_mandi_daily_prices.parquet` | 49,179 | 30 | 650,677 | `27bce2a9823f652758d76abc2c00454168a7a8567bf9e4ad15c3972153ad8382` |
| `data/processed/obs_ncrb_annual_crime_statistics.parquet` | 24 | 27 | 16,214 | `fa719e3697e95aa8a716d1a101115643a4de69b96933a22f554bd4f4458650a8` |
| `data/processed/obs_nfhs5_district_indicators.parquet` | 73,528 | 30 | 344,961 | `e244e0928a4272125a553a872b3cf74f2cecf675216683971af284c6c1a1be8a` |
| `data/processed/obs_plfs_state_ur_usual_status.parquet` | 190 | 27 | 20,833 | `0aabdeb6b5b63ab4d6562a7f2b51f52d884579303392df855f94508777878289` |
| `data/processed/plfs_state_ur_usual_status.parquet` | 38 | 8 | 6,572 | `b5ad91ebf6c7bae77ac00917dfea97706dc21dcd61b8af8f8e99049b706dde42` |

## Routing splits (`data/splits/kev`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/splits/kev/calibration.v1.jsonl` | 300 | - | 819,266 | `45995818623813e9927071140b2fb7faff08b98980d446b88410327bedf12ccc` |
| `data/splits/kev/dev_synthetic.v1.jsonl` | 338 | - | 924,222 | `e2f7aebd282e1220d3662864bf62080713e7f7cf93e61c7690a3bbd820f688c0` |
| `data/splits/kev/train.v1.jsonl` | 1,718 | - | 4,698,194 | `04c24468567c645c9959251866fc6f00f29338235af02e39a217be6df9a0226a` |

## Text-to-SQL ground truth (`data/ground_truths`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/ground_truths/text_to_sql_dev.v1.csv` | 63 | 9 | 23,088 | `b56f691a64f8f67c698d7dea68cc83a14f633e034a395a59ec343a4033589b1b` |
| `data/ground_truths/text_to_sql_ground_truth_100.csv` | 100 | 9 | 36,012 | `b093fdab96fe7f074061d77bcad73622f57c529194b4b71021792d428a6e9358` |
| `data/ground_truths/text_to_sql_test.v1.csv` | 37 | 9 | 13,028 | `255ff03526d59b72392a28e4c4d65c2ed7556dcea54ea54b41b1002e23660ce8` |

## Pipeline release (`data/processed/catalogue.json`)

Each table records the raw file it came from, the configuration version and the code
commit that produced it, so any figure can be traced back and reproduced.

| Dataset | Dataset version | Config | Raw SHA-256 | Code commit | Observation SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `imd_subdivision_monthly_rainfall` | `1.0.0+f655f42e` | 1.0.0 | `f655f42e672001c09fbd68ca14041f7299c76883d7aa9167400a1f963948bbad` | `7f58bed9a8ef` | `274fe27bb2575a43fad6fec6115895ee0d882f43502d47c9072fbbb7055d3ec3` |
| `mandi_daily_prices` | `1.0.0+6f5bb19d` | 1.0.0 | `6f5bb19d0814247222160ea24df581c982b74ff4608a2486cca5a9d62ad1b73d` | `7f58bed9a8ef` | `27bce2a9823f652758d76abc2c00454168a7a8567bf9e4ad15c3972153ad8382` |
| `ncrb_annual_crime_statistics` | `1.0.0+c04a05dd` | 1.0.0 | `c04a05dd3359fe8a024d73126f6abd51a7fc1c3802d68bc527490816f2205512` | `7f58bed9a8ef` | `fa719e3697e95aa8a716d1a101115643a4de69b96933a22f554bd4f4458650a8` |
| `nfhs5_district_indicators` | `1.0.0+de06b72f` | 1.0.0 | `de06b72f241fa9734676677a15941b93b890009b1c0f88be655b07e8a853a689` | `7f58bed9a8ef` | `e244e0928a4272125a553a872b3cf74f2cecf675216683971af284c6c1a1be8a` |
| `plfs_state_ur_usual_status` | `1.0.0+1c1b78de` | 1.0.0 | `1c1b78de7d20ff7d75e40701fc3b940f0804c80032ba25bf79a78d1fb030b1a6` | `7f58bed9a8ef` | `0aabdeb6b5b63ab4d6562a7f2b51f52d884579303392df855f94508777878289` |
