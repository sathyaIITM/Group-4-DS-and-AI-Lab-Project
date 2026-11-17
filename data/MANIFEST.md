# Data manifest

Produced by `scripts/build_manifest.py` on 2026-11-17. Recompute after regenerating any file; a changed hash means a changed version.

## Raw downloads (`data/raw`, not tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data\raw\cpi_all_india.csv` | 393 | 30 | 69,755 | `570d0899c81f2ccd5d3fe6ff421b316df084ec5708bdea55f6c93fada5342d09` |
| `data\raw\cpi_state.csv` | 441 | 39 | 93,240 | `2f860be773f42f8a344e106562ef6af86d4fff799a5fa2a6d7361d2f146e369a` |
| `data\raw\crop_production_district.csv` | 246,091 | 7 | 12,748,923 | `c0b2e3b0fb669c0a3fe88aebd1fe80a58abd4500151688e383df7e9e6fa95985` |
| `data\raw\datafile1.csv` | 707 | 109 | 356,689 | `de06b72f241fa9734676677a15941b93b890009b1c0f88be655b07e8a853a689` |
| `data\raw\datafile2.csv` | 16,393 | 10 | 1,577,826 | `6f5bb19d0814247222160ea24df581c982b74ff4608a2486cca5a9d62ad1b73d` |
| `data\raw\datafile3.csv` | 3 | 9 | 415 | `c04a05dd3359fe8a024d73126f6abd51a7fc1c3802d68bc527490816f2205512` |
| `data\raw\gsdp_per_capita_state.csv` | 28 | 7 | 1,474 | `6d28ac4c1aa8b5c4fd1433ff6a431a04b3a21a24c0eba6517f9f7f3d9a7f2fa7` |
| `data\raw\imd_district_rainfall_normals.csv` | 640 | 19 | 92,856 | `8f4417fd3707c6d0ecdb672330234f9c2d0cb895f00b1e53fb25d6775082ac6f` |
| `data\raw\imd_subdivision_monthly_rainfall.csv` | 4,188 | 19 | 441,180 | `f655f42e672001c09fbd68ca14041f7299c76883d7aa9167400a1f963948bbad` |
| `data\raw\msp_crops.csv` | 29 | 16 | 2,750 | `209586a358cf83d5922c57a0e42e15f6c3458fcde59b2c169eefbaceb6e42154` |
| `data\raw\nfhs5_state_factsheet.csv` | 110 | 137 | 126,922 | `97ac35bb4bbb908617a3fe91701d222db1acc8bf5a07bee88a1a435669c55ff7` |
| `data\raw\plfs_lfpr_urban_state.csv` | 37 | 3 | 816 | `3e347b0ba51f4864f331f98a358bd556d84e30cc96672a60c59aa34b694352c9` |
| `data\raw\plfs_state_ur_usual_status_2017_22.csv` | 38 | 7 | 1,340 | `1c1b78de7d20ff7d75e40701fc3b940f0804c80032ba25bf79a78d1fb030b1a6` |
| `data\raw\srs_imr_state.csv` | 37 | 7 | 1,403 | `6cd4d7123cb87a7066158de0e29516711bdf7f475c844422a9add3147812fc39` |

## Processed tables (`data/processed`, not tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data\processed\cpi_all_india.parquet` | 393 | 32 | 67,007 | `fb878ef22316523d1a26ae1698d636d04c99f9e6259ce363b9b35b22120aa04d` |
| `data\processed\crop_production_district.parquet` | 246,091 | 12 | 1,664,262 | `894d1c131b2d69887546f704b383d77871b04fb98e16b10a837d187dc642a2bf` |
| `data\processed\dim_period.parquet` | 47,482 | 6 | 433,722 | `86173a78af57c1d413c657c5929522d8410d7e2f56dd5c90dfaefe0199316ebc` |
| `data\processed\gsdp_per_capita_state.parquet` | 28 | 8 | 7,066 | `b57a6a2f016ba8f3f6237ea2615b55b408906b435250f934f3e4f16004917091` |
| `data\processed\imd_district_rainfall_normals.parquet` | 640 | 21 | 67,837 | `85681aa28027fee55d5714d23523223e4eab9ecc3c45fe78a3c4ea9722d46646` |
| `data\processed\imd_subdivision_monthly_rainfall.parquet` | 4,188 | 21 | 264,309 | `16af302b4883994ce84247443a05ce850385078cc26713ac9e145952c28dfe94` |
| `data\processed\mandi_daily_prices.parquet` | 16,393 | 23 | 191,450 | `edd91f6c1e5c0376cbe2660d3709c538787d24192f05fe4210de5bc99d63e08b` |
| `data\processed\msp_crops.parquet` | 29 | 17 | 12,305 | `d01bdd6e30caa1ce9c70558cc90b7fe0b65428f9e491d15c11090da7e5d9489e` |
| `data\processed\ncrb_annual_crime_statistics.parquet` | 3 | 23 | 14,227 | `f4c2a69990a57910f55492ded5cc15b8bc21e3f5591eefc937aa5a6f483fc47d` |
| `data\processed\nfhs5_district_indicators.parquet` | 73,528 | 21 | 312,155 | `579b4cd48e2934b969f63b85a8b0a7c286c5699e9106187cc56803a1556283d5` |
| `data\processed\nfhs5_state_factsheet.parquet` | 14,410 | 20 | 82,567 | `0cc159178a368c76a331da3162e4b97f3787b4bbb8a1339d07ba1e232fa318c4` |
| `data\processed\obs_cpi_all_india.parquet` | 10,611 | 28 | 63,979 | `5e014a7b46ee898125367df9e14af5987bb14adee9fcc9a8ac96349fc7646549` |
| `data\processed\obs_crop_production_district.parquet` | 492,182 | 29 | 4,988,584 | `bd17db7146c9b275c7915e781545be598b55fa8f2740f886115e5380dea5042e` |
| `data\processed\obs_gsdp_per_capita_state.parquet` | 140 | 27 | 20,559 | `1bef4065085048636e9646f9c573690a9ea375ced381e3dc1dfbc62636b5669b` |
| `data\processed\obs_imd_district_rainfall_normals.parquet` | 10,880 | 27 | 137,009 | `fcf81ee088c9d177bf98ad6c0f816fd8dfbf8040d66c086b5059913a235a4b05` |
| `data\processed\obs_imd_subdivision_monthly_rainfall.parquet` | 71,196 | 27 | 732,536 | `c4ed1a01b4d66f6554b29370d5039184b63c50b4e32c656bebbf0cd002293f1d` |
| `data\processed\obs_mandi_daily_prices.parquet` | 49,179 | 30 | 650,677 | `c0972ff648d47910773cee09e8b93fe04e3e8a059c246a66a9061366a9c612ec` |
| `data\processed\obs_msp_crops.parquet` | 348 | 30 | 21,294 | `827b2fe494a846f682d48818276b0e22e51e176739a47c15e361d60494263b1a` |
| `data\processed\obs_ncrb_annual_crime_statistics.parquet` | 24 | 27 | 16,214 | `2d20150aaa6ac2f1fd240f8123be5b870286a2a72ed15d8217414d2aeb5033fe` |
| `data\processed\obs_nfhs5_district_indicators.parquet` | 73,528 | 30 | 344,961 | `1debabb4d79e01beb9d71040e1aa7427a75c579f22f3147679205eec539addcc` |
| `data\processed\obs_nfhs5_state_factsheet.parquet` | 14,410 | 31 | 90,377 | `1c75010f66220006fe6a4d3eec7fb2429e68eed4860a7c2c138ad6dce9c5e532` |
| `data\processed\obs_plfs_lfpr_urban_state.parquet` | 37 | 27 | 18,898 | `6acb51ea02b1279c0fa472f2607255f661c15a0d27707c3a548688b510f1eb31` |
| `data\processed\obs_plfs_state_ur_usual_status.parquet` | 190 | 27 | 20,833 | `df5efa7e947821afcd5ba83fec16915f26807a4b130f337b07b5e4cd815ff66c` |
| `data\processed\obs_srs_imr_state.parquet` | 185 | 27 | 20,192 | `a34c57ab95ae7e701031f1ac3b229a0168680781b81b6f40ae10cd221774e476` |
| `data\processed\plfs_lfpr_urban_state.parquet` | 37 | 2 | 1,668 | `538585babe1c24fcd24afebf1f63d905e70db21e00049ab2038e4a949fdb06ef` |
| `data\processed\plfs_state_ur_usual_status.parquet` | 38 | 8 | 6,572 | `6bce9e995972419fa3d55510b393e3e4c3f5ff1d7ac89c88362241c132b5f2e6` |
| `data\processed\srs_imr_state.parquet` | 37 | 8 | 7,899 | `b529c2c56197b2029fa113177a8b29e0728de74da36991ad70eb7b20605003c3` |

## Routing splits (`data/splits/kev`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data\splits\kev\calibration.v1.jsonl` | 300 | - | 819,566 | `82f72d581d27bcd08e87ed5b7ce47045812187568923334edd835a51d022924b` |
| `data\splits\kev\dev_synthetic.v1.jsonl` | 338 | - | 924,560 | `e33e643719a4b224bc48a9a0f7213bfed03b8ec1af941bac11f9489a03fb27bf` |
| `data\splits\kev\train.v1.jsonl` | 1,718 | - | 4,699,912 | `fe4e573089c170ed30551e8a98ae02d94b3d6c2f6a112e25b1b1a3f0101988ad` |

## Text-to-SQL ground truth (`data/ground_truths`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data\ground_truths\text_to_sql_dev.v1.csv` | 63 | 9 | 23,182 | `8b6b6cae770547773b3619acc15a5bc435805d71310f6e5547c0b9134b9b8211` |
| `data\ground_truths\text_to_sql_ground_truth_100.csv` | 100 | 9 | 36,147 | `4f2d4f4b920e16d2bca75dc0edce5a434bc25eacfeaafcbca1ebc679e518523b` |
| `data\ground_truths\text_to_sql_test.v1.csv` | 37 | 9 | 13,070 | `f6990aa6f6ed1ff81b54188b8ebcea906a23f485604eec111cc9819fc945102a` |

## Pipeline release (`data/processed/catalogue.json`)

Each table records the raw file it came from, the configuration version and the code
commit that produced it, so any figure can be traced back and reproduced.

| Dataset | Dataset version | Config | Raw SHA-256 | Code commit | Observation SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `cpi_all_india` | `1.0.0+570d0899` | 1.0.0 | `570d0899c81f2ccd5d3fe6ff421b316df084ec5708bdea55f6c93fada5342d09` | `908a9affabb3` | `5e014a7b46ee898125367df9e14af5987bb14adee9fcc9a8ac96349fc7646549` |
| `crop_production_district` | `1.0.0+c0b2e3b0` | 1.0.0 | `c0b2e3b0fb669c0a3fe88aebd1fe80a58abd4500151688e383df7e9e6fa95985` | `c3fec1b32eb3` | `bd17db7146c9b275c7915e781545be598b55fa8f2740f886115e5380dea5042e` |
| `gsdp_per_capita_state` | `1.0.0+6d28ac4c` | 1.0.0 | `6d28ac4c1aa8b5c4fd1433ff6a431a04b3a21a24c0eba6517f9f7f3d9a7f2fa7` | `908a9affabb3` | `1bef4065085048636e9646f9c573690a9ea375ced381e3dc1dfbc62636b5669b` |
| `imd_district_rainfall_normals` | `1.0.0+8f4417fd` | 1.0.0 | `8f4417fd3707c6d0ecdb672330234f9c2d0cb895f00b1e53fb25d6775082ac6f` | `c3fec1b32eb3` | `fcf81ee088c9d177bf98ad6c0f816fd8dfbf8040d66c086b5059913a235a4b05` |
| `imd_subdivision_monthly_rainfall` | `1.0.0+f655f42e` | 1.0.0 | `f655f42e672001c09fbd68ca14041f7299c76883d7aa9167400a1f963948bbad` | `7c497cf1ab69` | `c4ed1a01b4d66f6554b29370d5039184b63c50b4e32c656bebbf0cd002293f1d` |
| `mandi_daily_prices` | `1.0.0+6f5bb19d` | 1.0.0 | `6f5bb19d0814247222160ea24df581c982b74ff4608a2486cca5a9d62ad1b73d` | `7c497cf1ab69` | `c0972ff648d47910773cee09e8b93fe04e3e8a059c246a66a9061366a9c612ec` |
| `msp_crops` | `1.0.0+209586a3` | 1.0.0 | `209586a358cf83d5922c57a0e42e15f6c3458fcde59b2c169eefbaceb6e42154` | `908a9affabb3` | `827b2fe494a846f682d48818276b0e22e51e176739a47c15e361d60494263b1a` |
| `ncrb_annual_crime_statistics` | `1.0.0+c04a05dd` | 1.0.0 | `c04a05dd3359fe8a024d73126f6abd51a7fc1c3802d68bc527490816f2205512` | `7c497cf1ab69` | `2d20150aaa6ac2f1fd240f8123be5b870286a2a72ed15d8217414d2aeb5033fe` |
| `nfhs5_district_indicators` | `1.0.0+de06b72f` | 1.0.0 | `de06b72f241fa9734676677a15941b93b890009b1c0f88be655b07e8a853a689` | `7c497cf1ab69` | `1debabb4d79e01beb9d71040e1aa7427a75c579f22f3147679205eec539addcc` |
| `nfhs5_state_factsheet` | `1.0.0+97ac35bb` | 1.0.0 | `97ac35bb4bbb908617a3fe91701d222db1acc8bf5a07bee88a1a435669c55ff7` | `908a9affabb3` | `1c75010f66220006fe6a4d3eec7fb2429e68eed4860a7c2c138ad6dce9c5e532` |
| `plfs_lfpr_urban_state` | `1.0.0+3e347b0b` | 1.0.0 | `3e347b0ba51f4864f331f98a358bd556d84e30cc96672a60c59aa34b694352c9` | `908a9affabb3` | `6acb51ea02b1279c0fa472f2607255f661c15a0d27707c3a548688b510f1eb31` |
| `plfs_state_ur_usual_status` | `1.0.0+1c1b78de` | 1.0.0 | `1c1b78de7d20ff7d75e40701fc3b940f0804c80032ba25bf79a78d1fb030b1a6` | `7c497cf1ab69` | `df5efa7e947821afcd5ba83fec16915f26807a4b130f337b07b5e4cd815ff66c` |
| `srs_imr_state` | `1.0.0+6cd4d712` | 1.0.0 | `6cd4d7123cb87a7066158de0e29516711bdf7f475c844422a9add3147812fc39` | `908a9affabb3` | `a34c57ab95ae7e701031f1ac3b229a0168680781b81b6f40ae10cd221774e476` |
