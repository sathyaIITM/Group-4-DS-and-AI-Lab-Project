# Data manifest

Produced by `scripts/build_manifest.py` on 2026-11-17. Recompute after regenerating any file; a changed hash means a changed version.

## Raw downloads (`data/raw`, not tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/raw/cpi_all_india.csv` | 393 | 30 | 69,754 | `5eff4272f8729dbe973569068d2063ccc05994a0bbead29711e74e8c84f306b1` |
| `data/raw/cpi_state.csv` | 441 | 39 | 93,235 | `ac786313cb19629e348796f79e48e11507fbdcce3385b53d3b5f922cdf68692c` |
| `data/raw/crop_production_district.csv` | 246,091 | 7 | 12,748,923 | `c0b2e3b0fb669c0a3fe88aebd1fe80a58abd4500151688e383df7e9e6fa95985` |
| `data/raw/datafile1.csv` | 707 | 109 | 356,689 | `de06b72f241fa9734676677a15941b93b890009b1c0f88be655b07e8a853a689` |
| `data/raw/datafile2.csv` | 16,393 | 10 | 1,577,826 | `6f5bb19d0814247222160ea24df581c982b74ff4608a2486cca5a9d62ad1b73d` |
| `data/raw/datafile3.csv` | 3 | 9 | 415 | `c04a05dd3359fe8a024d73126f6abd51a7fc1c3802d68bc527490816f2205512` |
| `data/raw/gsdp_per_capita_state.csv` | 28 | 7 | 1,474 | `6d28ac4c1aa8b5c4fd1433ff6a431a04b3a21a24c0eba6517f9f7f3d9a7f2fa7` |
| `data/raw/imd_district_rainfall_normals.csv` | 641 | 19 | 69,259 | `18e47de2a0598600d53f2e6cd0130b518cef9a623ec625d2ec764e512755580b` |
| `data/raw/imd_subdivision_monthly_rainfall.csv` | 4,188 | 19 | 441,180 | `f655f42e672001c09fbd68ca14041f7299c76883d7aa9167400a1f963948bbad` |
| `data/raw/msp_crops.csv` | 29 | 16 | 2,750 | `209586a358cf83d5922c57a0e42e15f6c3458fcde59b2c169eefbaceb6e42154` |
| `data/raw/ncrb_violent_crimes_state.csv` | 39 | 8 | 1,962 | `a106fe328b5f08b571755f540a6887cfd75ea83af509615a36b3b1828d79aa00` |
| `data/raw/nfhs5_state_factsheet.csv` | 111 | 136 | 80,216 | `03e7cb0fff3688a03483372375cda18294433272fae3e8cf8421c6f5ffb1e3d5` |
| `data/raw/plfs_lfpr_urban_state.csv` | 37 | 3 | 816 | `3e347b0ba51f4864f331f98a358bd556d84e30cc96672a60c59aa34b694352c9` |
| `data/raw/plfs_state_ur_usual_status_2017_22.csv` | 38 | 7 | 1,340 | `1c1b78de7d20ff7d75e40701fc3b940f0804c80032ba25bf79a78d1fb030b1a6` |
| `data/raw/srs_imr_state.csv` | 37 | 7 | 1,403 | `6cd4d7123cb87a7066158de0e29516711bdf7f475c844422a9add3147812fc39` |

## Processed tables (`data/processed`, not tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/processed/cpi_all_india.parquet` | 393 | 32 | 67,007 | `f37ba7b8a54646aff0a289e879130b22fb600b82598eb09e01464c432837ab6b` |
| `data/processed/crop_production_district.parquet` | 246,091 | 12 | 1,664,262 | `d8c7297731ba939c61b695019b3e8d25c8180ec02e7f87367c58fca2db114691` |
| `data/processed/dim_period.parquet` | 47,482 | 6 | 433,722 | `d57333207a4129b786b06391ca5fee0292db098a8ced5aa17affcdef47cfacfe` |
| `data/processed/gsdp_per_capita_state.parquet` | 28 | 8 | 7,066 | `420cc7086a0a6e4ddd40610feb77c1b1521a303e8a0c39af0e2c83ad502477cd` |
| `data/processed/imd_district_rainfall_normals.parquet` | 641 | 21 | 68,083 | `6193d16f4a70d6c2964cf7840438664ce6487e46223404a35e9d0ae406d084f9` |
| `data/processed/imd_subdivision_monthly_rainfall.parquet` | 4,188 | 21 | 264,309 | `aebf88a7faa13d4ce8052316d0a9b6764220c71b70d947556963b0fb029925e8` |
| `data/processed/mandi_daily_prices.parquet` | 16,393 | 23 | 191,450 | `f7890ca7e7a25a029a5632cc39c613430a35acb0150e55bd1f72a7011edbe371` |
| `data/processed/msp_crops.parquet` | 29 | 17 | 12,305 | `e3f7524b6154cde80b3016da978a035a1a67aaef92ca8a63f11c52db95fa4d49` |
| `data/processed/ncrb_annual_crime_statistics.parquet` | 3 | 23 | 14,227 | `1787a31d588c0d13979f4c1300fbef1f519d298e0eb9fbcabaf9a5cc94d2b912` |
| `data/processed/ncrb_violent_crimes_state.parquet` | 37 | 6 | 4,989 | `1d4c2ba3b84372f81d66e18f04af528bffb91ded4ba7dc753c221f7f39229d86` |
| `data/processed/nfhs5_district_indicators.parquet` | 73,528 | 21 | 311,836 | `741f566e5a7bb8b23c0d0cc99ca2eb7b6f5507e0f669907b0664db9a58841159` |
| `data/processed/nfhs5_state_factsheet.parquet` | 14,541 | 20 | 82,526 | `15189923d6dfa4a2b0f33208ed8787fa03b6da828c77c98443714259b83484d0` |
| `data/processed/obs_cpi_all_india.parquet` | 10,611 | 28 | 63,979 | `e852acf2fe18ee4b064a116973889bc526513e8cdd68c5b5879f20e1183e6399` |
| `data/processed/obs_crop_production_district.parquet` | 492,182 | 29 | 4,988,584 | `7a17c50ffa5fbb836d6be1db5d24d88d24c554021abe719bcd50ffdbe4e3c627` |
| `data/processed/obs_gsdp_per_capita_state.parquet` | 140 | 27 | 20,559 | `5f0a25e002120f4245c0d72da63c7ceb054105a4ed1d1bb394b8e1c416b504ea` |
| `data/processed/obs_imd_district_rainfall_normals.parquet` | 10,897 | 27 | 137,245 | `8a714f9be3e633a0030fbd4137162a7ca4a7ed049fc156e13a93f7674cc85cd8` |
| `data/processed/obs_imd_subdivision_monthly_rainfall.parquet` | 71,196 | 27 | 732,536 | `274fe27bb2575a43fad6fec6115895ee0d882f43502d47c9072fbbb7055d3ec3` |
| `data/processed/obs_mandi_daily_prices.parquet` | 49,179 | 30 | 650,677 | `27bce2a9823f652758d76abc2c00454168a7a8567bf9e4ad15c3972153ad8382` |
| `data/processed/obs_msp_crops.parquet` | 348 | 30 | 21,294 | `a0dc224a0c60fba1e8f0e624e0428015b4fec34febaed7c8613790634c97abad` |
| `data/processed/obs_ncrb_annual_crime_statistics.parquet` | 24 | 27 | 16,214 | `fa719e3697e95aa8a716d1a101115643a4de69b96933a22f554bd4f4458650a8` |
| `data/processed/obs_ncrb_violent_crimes_state.parquet` | 111 | 27 | 20,313 | `e9d12ef00912492ed8b159e705bfebb4986746d4d79f92db9541e92b5bc57a9d` |
| `data/processed/obs_nfhs5_district_indicators.parquet` | 73,528 | 30 | 344,915 | `8d44f06e0ef1c46bc392344bdcc034c93cac0f20e929c027a3b5edfe9ba45afb` |
| `data/processed/obs_nfhs5_state_factsheet.parquet` | 14,541 | 31 | 90,324 | `93fe35cdd19a4230c22ab30c28153bddce43ff7757417fa9e8a868aa8d3dd629` |
| `data/processed/obs_plfs_lfpr_urban_state.parquet` | 37 | 27 | 18,898 | `c7d70738ccdf65ec8282fa75343fbe0a9d10f73a70e0d0fd3de162e8eb6809d9` |
| `data/processed/obs_plfs_state_ur_usual_status.parquet` | 190 | 27 | 20,833 | `0aabdeb6b5b63ab4d6562a7f2b51f52d884579303392df855f94508777878289` |
| `data/processed/obs_srs_imr_state.parquet` | 185 | 27 | 20,192 | `c4f3fc95ee5eec0bb470a1447abf00c2897be1f48e02565dfe3297b6f5b6d270` |
| `data/processed/plfs_lfpr_urban_state.parquet` | 37 | 2 | 1,668 | `dee32cd1760d74540d7283aefaa7fbbb35819868722668e68134f1a90038c446` |
| `data/processed/plfs_state_ur_usual_status.parquet` | 38 | 8 | 6,572 | `b5ad91ebf6c7bae77ac00917dfea97706dc21dcd61b8af8f8e99049b706dde42` |
| `data/processed/srs_imr_state.parquet` | 37 | 8 | 7,899 | `073999531c0e6bc1a4f372e9bb4231522d6326b315149647369130407ffd1280` |

## Routing splits, version 1 (`data/splits/kev`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/splits/kev/calibration.v1.jsonl` | 300 | - | 819,266 | `45995818623813e9927071140b2fb7faff08b98980d446b88410327bedf12ccc` |
| `data/splits/kev/dev_synthetic.v1.jsonl` | 338 | - | 924,222 | `e2f7aebd282e1220d3662864bf62080713e7f7cf93e61c7690a3bbd820f688c0` |
| `data/splits/kev/train.v1.jsonl` | 1,718 | - | 4,698,194 | `04c24468567c645c9959251866fc6f00f29338235af02e39a217be6df9a0226a` |

## Routing splits, version 2, frozen catalogue (`data/splits/kev`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/splits/kev/calibration.v2.jsonl` | 322 | - | 1,054,950 | `f1a8fafc64fa829e3fde12375a262366658cec7b9d0faa43af3ce58c4c4b5c2f` |
| `data/splits/kev/dev_synthetic.v2.jsonl` | 355 | - | 1,172,802 | `3a249faf05ac85c099a45a4c6a0d522cbd17df7918186a80f3edfc7f7db9fac3` |
| `data/splits/kev/train.v2.jsonl` | 1,876 | - | 6,048,918 | `4829691c1b21b5243185fb308e882e7e490e199bf1a67d649e6eeaf6f29ca427` |

## Domain-only Kev files, version 2 (`data/splits/kev_domain`, not tracked; `python scripts/build_domain_phase1.py --version v2 --laya`)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/splits/kev_domain/calibration.v2.jsonl` | 322 | - | 645,896 | `8d363f6e8c3e34e699041d2f2cce3c85c01ced239574a02e37a016790c3bdcba` |
| `data/splits/kev_domain/dev_synthetic.v2.jsonl` | 355 | - | 721,987 | `2fa6eaf2e18df3c9c3a9fc95836487e194154500c5953340f5fc0d6496c48a17` |
| `data/splits/kev_domain/overfit32.v2.jsonl` | 32 | - | 64,170 | `fafb70ccd0201b351efa0fd3608f43f2e3ac5e83fdb2b91a80236fd84f72eaee` |
| `data/splits/kev_domain/train.v2.jsonl` | 1,876 | - | 3,666,000 | `bd762f0f56dde25df964eadcaf2cd4a95a939ff059e3d2aa15daccfd7e79a54f` |
| `data/splits/kev_domain/train250.v2.jsonl` | 250 | - | 491,693 | `f8aa13685b2e6a0606eea0dc7fc10dba588bd568253d5ef84dc7d2517c9717e9` |

## Domain-only Laya rows, version 2 (`data/splits/laya_domain`, not tracked; same command)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/splits/laya_domain/calibration.v2.jsonl` | 322 | - | 511,837 | `9e82c4742f8fef5ec94463f07b9b36a572cb4ddccf6984f213e5c7ac9e5f34b8` |
| `data/splits/laya_domain/dev_synthetic.v2.jsonl` | 355 | - | 570,015 | `de2fd4b25a28a89e1c1fbbf6ad18a2dc93728662624b2689290da6d33eaf1016` |
| `data/splits/laya_domain/overfit32.v2.jsonl` | 32 | - | 51,045 | `a7a54b1b9cbc72ecd2863a727079b09dbd6bb40c897dc6bbc2a95e759d0ddd1c` |
| `data/splits/laya_domain/train.v2.jsonl` | 1,876 | - | 2,905,996 | `5234bcedfb1512243c8ec1c10203ce3064db1ad0458a8dee77765cc45cfe5892` |
| `data/splits/laya_domain/train250.v2.jsonl` | 250 | - | 389,111 | `60b4b976bc1f195a52a59320980ebb2bc8f43105ad7c45622e74f285ed0508c7` |

## Parity phase training files (Milestone 5; not tracked)

Written by `~/kev-src/.venv/bin/python -I scripts/build_parity_data.py --kev-src ~/kev-src --root .`
(protocol `docs/specs/kev_laya_parity_protocol.md`). The Laya files hold the Kev-augmented variants of
every epoch (gzip-compressed JSONL); every hash is also in `data/splits/laya_parity/hashes.json`.

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/splits/kev/phase2_split/train_heldout_srs_imr_state.v2.jsonl` | 3,656 | - | 8,381,306 | `ba57c49b538eab573bbc96a45407584301f7d33455e86972dcf14acd56a7ef71` |
| `data/splits/laya_parity/domain/s0_e2.jsonl.gz` | 3,752 | - | 229,435 | `20a399442b6e6ece0a99942bb562403b8d98cd7588c66d8438bc79642fa58a86` |
| `data/splits/laya_parity/domain/s0_e4.jsonl.gz` | 7,504 | - | 458,268 | `ec9f7c7162d0fedf0f71c1ba6a3d29450283dd67b197eb09dd96dda35ba2b157` |
| `data/splits/laya_parity/domain/s0_e6.jsonl.gz` | 11,256 | - | 686,668 | `75d2a0c55bdfec9f2a5217ab1f8124abb6e5a25fac53ad0ad6887c744119594f` |
| `data/splits/laya_parity/domain/s1_e2.jsonl.gz` | 3,752 | - | 228,946 | `819d6afc71b9acfc0f57ee7074ec87af3ac0f2bf8a4df6f47cb35900b7161a65` |
| `data/splits/laya_parity/domain/s1_e4.jsonl.gz` | 7,504 | - | 457,744 | `9f6bbd8733d01e1c2274ca26b3283e7f406f3afe8f52fd276c917c1298a1a93a` |
| `data/splits/laya_parity/domain/s1_e6.jsonl.gz` | 11,256 | - | 685,955 | `760095acd4e9192ad3511e03938b25327bcaba576a27a5549bf721187c67c883` |
| `data/splits/laya_parity/domain/s2_e2.jsonl.gz` | 3,752 | - | 229,655 | `032dc8ab8538ba42dcaf1d95f9adbd2d0575090b96c76001ac59ee00ebfe6dfe` |
| `data/splits/laya_parity/domain/s2_e4.jsonl.gz` | 7,504 | - | 457,894 | `9cf598cf5572730f050a90fa4ac234ab7cd233dd008dc4ca00fc2aa7faec0bed` |
| `data/splits/laya_parity/domain/s2_e6.jsonl.gz` | 11,256 | - | 686,677 | `08156067c80d83910ceccced4c031fd4156cbaa5c4c2ebe87f658b30d04e00ed` |
| `data/splits/laya_parity/joint/s0_e2.jsonl.gz` | 7,504 | - | 430,576 | `5115bc34a87665ae1b499e42a81e4d6d027aeb1047a3682e7b45364cb48c2a55` |
| `data/splits/laya_parity/joint/s0_e4.jsonl.gz` | 15,008 | - | 860,085 | `26d41dbf7693dfe70d09885677f9111d93af9abb8f8309405c856094c2cd1db8` |
| `data/splits/laya_parity/joint/s0_e6.jsonl.gz` | 22,512 | - | 1,289,361 | `fa1055634ae523b423ba9b471e66b3c05f7244a96dd69acb4568806f450f4a45` |
| `data/splits/laya_parity/joint/s1_e2.jsonl.gz` | 7,504 | - | 429,491 | `d77fdf0e15d83171edc52fa23a41e84dbafd8f84bf6f1d7a5856bfc8719682bf` |
| `data/splits/laya_parity/joint/s1_e4.jsonl.gz` | 15,008 | - | 859,124 | `d2613151a07968cbbafba4f7ebd5993fe91b62d8a74304ede96044a17482b287` |
| `data/splits/laya_parity/joint/s1_e6.jsonl.gz` | 22,512 | - | 1,287,993 | `c5369b9b6595a28476bb3a76c61a38d7824dfb4983bc73bfca90e936882caff1` |
| `data/splits/laya_parity/joint/s2_e2.jsonl.gz` | 7,504 | - | 430,865 | `04283967ff2ec197b99408dc2b4a2adc2b40efc725682022522e0dd303e6a4a4` |
| `data/splits/laya_parity/joint/s2_e4.jsonl.gz` | 15,008 | - | 859,824 | `0ec582fd084090aa6f541bbb9ed645d2d584f6fb0b53510aea601f066a37ebf4` |
| `data/splits/laya_parity/joint/s2_e6.jsonl.gz` | 22,512 | - | 1,288,932 | `517e829f4f81c2390cf8f113073820010d57236d970da9f1ffaf646ec2839603` |
| `data/splits/laya_parity/joint_heldout/s0_e2.jsonl.gz` | 7,312 | - | 420,082 | `3a21ece98719d8c24f17f9224fb4608e6e3a21d74f7b7a177a3042cd03c8859f` |
| `data/splits/laya_parity/joint_heldout/s0_e4.jsonl.gz` | 14,624 | - | 839,024 | `b7f9535286466218771aed2d274b01b91b41c25b36709720977a7344e43eec85` |
| `data/splits/laya_parity/joint_heldout/s0_e6.jsonl.gz` | 21,936 | - | 1,257,751 | `d2db5dacc898a0b43eb9f8bc9459dd8880c45cffe272c368ee34399ee2ec2a2d` |
| `data/splits/laya_parity/joint_heldout/s1_e2.jsonl.gz` | 7,312 | - | 419,403 | `4b168f89a5612632516d826aeda10bab80cf86ccfbdcc6b1770395e70debcc55` |
| `data/splits/laya_parity/joint_heldout/s1_e4.jsonl.gz` | 14,624 | - | 838,660 | `1b7feddaa0912cd0ee87157d8e839428142156ff3a7fb0258950f01932b7ab6c` |
| `data/splits/laya_parity/joint_heldout/s1_e6.jsonl.gz` | 21,936 | - | 1,257,114 | `2cded0377063364a94a83ca108bd3a9b59c050ebccb46b17862c706fde1fb700` |
| `data/splits/laya_parity/joint_heldout/s2_e2.jsonl.gz` | 7,312 | - | 420,464 | `ca1a38e9b127ba6dee118f82413f15175fe06460a5d4d9d79984cc7cd77fd177` |
| `data/splits/laya_parity/joint_heldout/s2_e4.jsonl.gz` | 14,624 | - | 838,813 | `94486525262aefa77d13230f8a2b4199c18958804ebce4b2326a1b0de1d7701e` |
| `data/splits/laya_parity/joint_heldout/s2_e6.jsonl.gz` | 21,936 | - | 1,257,636 | `542edfc1b57fc57e051fa83ac644f624189c7219ca877f09d164d9e80a1ecac8` |

### Run plans of the parity phase (`outputs/reports/parity_plans`, tracked)

The plan each Kaggle session ran, copied unchanged from the staged upload folder
(`outputs/drive_stage/Group4/...`). Each plan records the repository commit it was made from and
the SHA-256 of every file it uses; the notebooks refuse any file whose hash differs. Commits are
the pre-rebase hashes, kept on branch `archive/t3-m5-parity-runs`.

| File | Session | Runs | Made from | Bytes | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `outputs/reports/parity_plans/laya_K1_sweep.json` | Laya K1 (sweep) | 7 | `3833177`, clean | 6,767 | `d0fb9bee1f834174c4546c621c1f5015ec2b8b219ac5041e06aab84400e50a7c` |
| `outputs/reports/parity_plans/laya_K3_finals.json` | Laya K3 (finals, 3 parts) | 11 | `57d6124`, clean | 11,656 | `73f73814d4ab2665468b532a3c08745fe4c8edcb4a4236b79f4f58bf5c082030` |
| `outputs/reports/parity_plans/kev_kaggle_5.json` | Kev `kaggle_5` (joint, held-out) | 5 of 19 listed | `3833177`, clean | 24,718 | `d8980132a679bc216e477198c6f9829a5cab210eb9c8ab33c244f414cbc7c407` |
| `outputs/reports/parity_plans/kev_kaggle_6.json` | Kev `kaggle_6` (domain seeds) | 4 of 19 listed | `3833177`, working tree holding exactly the change committed as `802b1a0` | 24,601 | `498b0329a661da38aed3726ae1663e0902af36719aeb693eca9d408eb3a0bed9` |

## dev_human items and rendered states (`data/labels/dev_human_v1`, tracked)

| File | Rows | Columns | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/labels/dev_human_v1/items.jsonl` | 200 | - | 34,145 | `190f75f034add0d9d6fc8ca9169c82f4d1bd3b121a13d1b28a35a9cc90e23d39` |
| `data/labels/dev_human_v1/items_rendered.jsonl` | 200 | - | 183,904 | `4b13e28f4b3345eabb967a9cda2f844fe9d1621ba42ab9dd7c558dce38ac4c17` |
| `data/labels/dev_human_v1/relabel_tool_v1_1.csv` (D17: tool re-adjudication under guide 1.1; 50 items, 0 changed, so the v1.1 tool labels equal v1) | 50 | 5 | 8,386 | `d2b4c9b8b05fd9f9792cd95c45dfa781b85d73362f6b81d9bce1b8e196110409` |

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
| `cpi_all_india` | `1.0.0+5eff4272` | 1.0.0 | `5eff4272f8729dbe973569068d2063ccc05994a0bbead29711e74e8c84f306b1` | `e69082b91668` | `e852acf2fe18ee4b064a116973889bc526513e8cdd68c5b5879f20e1183e6399` |
| `crop_production_district` | `1.0.0+c0b2e3b0` | 1.0.0 | `c0b2e3b0fb669c0a3fe88aebd1fe80a58abd4500151688e383df7e9e6fa95985` | `e69082b91668` | `7a17c50ffa5fbb836d6be1db5d24d88d24c554021abe719bcd50ffdbe4e3c627` |
| `gsdp_per_capita_state` | `1.0.0+6d28ac4c` | 1.0.0 | `6d28ac4c1aa8b5c4fd1433ff6a431a04b3a21a24c0eba6517f9f7f3d9a7f2fa7` | `e69082b91668` | `5f0a25e002120f4245c0d72da63c7ceb054105a4ed1d1bb394b8e1c416b504ea` |
| `imd_district_rainfall_normals` | `1.0.0+18e47de2` | 1.0.0 | `18e47de2a0598600d53f2e6cd0130b518cef9a623ec625d2ec764e512755580b` | `e69082b91668` | `8a714f9be3e633a0030fbd4137162a7ca4a7ed049fc156e13a93f7674cc85cd8` |
| `imd_subdivision_monthly_rainfall` | `1.0.0+f655f42e` | 1.0.0 | `f655f42e672001c09fbd68ca14041f7299c76883d7aa9167400a1f963948bbad` | `e69082b91668` | `274fe27bb2575a43fad6fec6115895ee0d882f43502d47c9072fbbb7055d3ec3` |
| `mandi_daily_prices` | `1.0.0+6f5bb19d` | 1.0.0 | `6f5bb19d0814247222160ea24df581c982b74ff4608a2486cca5a9d62ad1b73d` | `e69082b91668` | `27bce2a9823f652758d76abc2c00454168a7a8567bf9e4ad15c3972153ad8382` |
| `msp_crops` | `1.0.0+209586a3` | 1.0.0 | `209586a358cf83d5922c57a0e42e15f6c3458fcde59b2c169eefbaceb6e42154` | `e69082b91668` | `a0dc224a0c60fba1e8f0e624e0428015b4fec34febaed7c8613790634c97abad` |
| `ncrb_annual_crime_statistics` | `1.0.0+c04a05dd` | 1.0.0 | `c04a05dd3359fe8a024d73126f6abd51a7fc1c3802d68bc527490816f2205512` | `e69082b91668` | `fa719e3697e95aa8a716d1a101115643a4de69b96933a22f554bd4f4458650a8` |
| `ncrb_violent_crimes_state` | `1.0.0+a106fe32` | 1.0.0 | `a106fe328b5f08b571755f540a6887cfd75ea83af509615a36b3b1828d79aa00` | `e69082b91668` | `e9d12ef00912492ed8b159e705bfebb4986746d4d79f92db9541e92b5bc57a9d` |
| `nfhs5_district_indicators` | `1.0.1+de06b72f` | 1.0.1 | `de06b72f241fa9734676677a15941b93b890009b1c0f88be655b07e8a853a689` | `e69082b91668` | `8d44f06e0ef1c46bc392344bdcc034c93cac0f20e929c027a3b5edfe9ba45afb` |
| `nfhs5_state_factsheet` | `1.1.2+03e7cb0f` | 1.1.2 | `03e7cb0fff3688a03483372375cda18294433272fae3e8cf8421c6f5ffb1e3d5` | `e69082b91668` | `93fe35cdd19a4230c22ab30c28153bddce43ff7757417fa9e8a868aa8d3dd629` |
| `plfs_lfpr_urban_state` | `1.0.0+3e347b0b` | 1.0.0 | `3e347b0ba51f4864f331f98a358bd556d84e30cc96672a60c59aa34b694352c9` | `e69082b91668` | `c7d70738ccdf65ec8282fa75343fbe0a9d10f73a70e0d0fd3de162e8eb6809d9` |
| `plfs_state_ur_usual_status` | `1.0.0+1c1b78de` | 1.0.0 | `1c1b78de7d20ff7d75e40701fc3b940f0804c80032ba25bf79a78d1fb030b1a6` | `e69082b91668` | `0aabdeb6b5b63ab4d6562a7f2b51f52d884579303392df855f94508777878289` |
| `srs_imr_state` | `1.0.0+6cd4d712` | 1.0.0 | `6cd4d7123cb87a7066158de0e29516711bdf7f475c844422a9add3147812fc39` | `e69082b91668` | `c4f3fc95ee5eec0bb470a1447abf00c2897be1f48e02565dfe3297b6f5b6d270` |
