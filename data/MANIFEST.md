# Data manifest

Produced by `scripts/build_manifest.py` on 2026-10-29. Recompute after regenerating any file; a changed hash means a changed version.

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
| `data/processed/imd_subdivision_monthly_rainfall.parquet` | 4,188 | 19 | 263,091 | `9db782cb7ef9af0b48c3e2e5b3ef63f106c28ee2782c919e261f008f1fb02891` |
| `data/processed/mandi_daily_prices.parquet` | 16,393 | 22 | 190,830 | `74fccb849339cd9592ccf882c148ab0080f380415123d0b26c15120ed1aebd8e` |
| `data/processed/ncrb_annual_crime_statistics.parquet` | 3 | 22 | 13,767 | `e4878fad6dbc66a01e079d5ccd552f8b48b2c3880772249e72d7539af0364f6b` |
| `data/processed/nfhs5_district_indicators.parquet` | 73,528 | 20 | 306,379 | `8308c32c297eafa03dd9ef8129e6a3a97a86d81b5cd88fb6df195af0eda73731` |
| `data/processed/plfs_state_ur_usual_status.parquet` | 38 | 6 | 5,453 | `02294673edc08311080cac3c3ead40fc4609a6e0b0d2c71a0847bc77b66f6dab` |

## Routing splits (`data/splits/kev`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/splits/kev/calibration.v1.jsonl` | 300 | - | 819,266 | `45995818623813e9927071140b2fb7faff08b98980d446b88410327bedf12ccc` |
| `data/splits/kev/dev_synthetic.v1.jsonl` | 338 | - | 924,222 | `e2f7aebd282e1220d3662864bf62080713e7f7cf93e61c7690a3bbd820f688c0` |
| `data/splits/kev/train.v1.jsonl` | 1,718 | - | 4,698,194 | `04c24468567c645c9959251866fc6f00f29338235af02e39a217be6df9a0226a` |

## Text-to-SQL ground truth (`data/ground_truths`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/ground_truths/text_to_sql_dev.v1.csv` | 63 | 9 | 23,085 | `2822aaf23f206c0f1794646c225372d2361cdc8f49b8856116c009d0b18a9385` |
| `data/ground_truths/text_to_sql_ground_truth_100.csv` | 100 | 9 | 36,009 | `8cde2a370109d3eaa0153b8bea82631828e0b501b68f0bfe74efb8d9a52a5d60` |
| `data/ground_truths/text_to_sql_test.v1.csv` | 37 | 9 | 13,028 | `255ff03526d59b72392a28e4c4d65c2ed7556dcea54ea54b41b1002e23660ce8` |
