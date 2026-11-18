# Kev-0.8B domain runs: comparison

Produced by `python -m analyst.models.kev_report table` from `models/registry.json` and
`outputs/reports/score_domain_<run>.json`. dev = dev_synthetic (rule and teacher
labels); accuracy and macro-F1 are unchanged by temperature; dev NLL is after the
temperature fitted on calibration.

| run_id | factor | platform | init | lr | epochs | seed | wall_min | peak_gb | clipped_share | final_train_loss | calibration_nll_raw | temperature | dev_accuracy | dev_macro_f1 | dev_nll | dev_ece_raw | dev_ece_calibrated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b0_s0 | b0 | kaggle | kev-0.8b | 2e-05 | 2 | 0 | 35.1 | 6.79 | 0.445 | 0.086 | 0.254 | 3.474 | 0.992 | 0.986 | 0.035 | 0.00782 | 0.013 |
| b0_s1 | seed | kaggle | kev-0.8b | 2e-05 | 2 | 1 | 34.6 | 6.79 | 0.44 | 0.102 | 0.345 | 3.917 | 0.992 | 0.986 | 0.037 | 0.00665 | 0.02 |
| b0_s2 | seed | kaggle | kev-0.8b | 2e-05 | 2 | 2 | 35.2 | 6.78 | 0.44 | 0.2 | 0.288 | 3.763 | 0.992 | 0.986 | 0.053 | 0.0068 | 0.016 |
| base_r16 | from_base_lora | colab | base | 0.0002 | 2 | 0 | 37 | 6.79 | 0.374 | 0.009 | 0.126 | 3.544 | 0.989 | 0.98 | 0.033 | 0.011 | 0.00553 |
| ep1 | epochs | kaggle | kev-0.8b | 2e-05 | 1 | 0 | 17.6 | 6.74 | 0.774 | 0.194 | 0.349 | 2.599 | 0.966 | 0.948 | 0.14 | 0.016 | 0.055 |
| ep3 | epochs | kaggle | kev-0.8b | 2e-05 | 3 | 0 | 53 | 6.79 | 0.329 | 0.001 | 0.234 | 3.763 | 0.994 | 0.991 | 0.024 | 0.00522 | 0.00896 |
| lr1e-05 | lr | kaggle | kev-0.8b | 1e-05 | 2 | 0 | 35.8 | 6.79 | 0.711 | 0.153 | 0.322 | 2.931 | 0.986 | 0.979 | 0.076 | 0.011 | 0.037 |
| lr4e-05 | lr | kaggle | kev-0.8b | 4e-05 | 2 | 0 | 34.6 | 6.79 | 0.34 | 0.001 | 0.134 | 3.474 | 0.994 | 0.991 | 0.025 | 0.00767 | 0.00655 |
