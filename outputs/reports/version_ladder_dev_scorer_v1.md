Version ladder on `e2e_dev` (scorer rules v1): mean over runs (minimum to maximum).

| Measure | v0 | v1 | v2 |
| --- | --- | --- | --- |
| Success | 0.933 | 0.917 | 0.967 |
| Execution accuracy | 0.703 | 0.703 | 0.865 |
| Wrong-answer rate | 0.029 | 0.029 | 0.000 |
| Abstention precision | 0.933 | 0.929 | 0.938 |
| Abstention recall | 0.933 | 0.867 | 1.000 |
| Latency p50 (s) | 6.8 | 6.7 | 5.7 |
| Latency p95 (s) | 9.7 | 10.7 | 10.7 |
| Cost per answer (USD, est.) | 0.0220 | 0.0227 | 0.0174 |
| Model calls per answer | 7.09 | 7.06 | 5.17 |
| Runs x questions | 1 x 60 | 1 x 60 | 1 x 60 |
| Run-to-run instability | 0.000 | 0.000 | 0.000 |

Success by expected action (all runs pooled; cases in brackets).

| Expected action | v0 | v1 | v2 |
| --- | --- | --- | --- |
| answer | 0.919 (37) | 0.919 (37) | 0.946 (37) |
| clarify | 0.833 (6) | 0.833 (6) | 1.000 (6) |
| decline | 1.000 (9) | 0.889 (9) | 1.000 (9) |
| describe | 1.000 (4) | 1.000 (4) | 1.000 (4) |
| search | 1.000 (4) | 1.000 (4) | 1.000 (4) |
