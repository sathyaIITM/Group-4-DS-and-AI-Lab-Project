Version ladder on `e2e_test` (scorer rules v2): mean over runs (minimum to maximum).

| Measure | v0 | v1 | v2 |
| --- | --- | --- | --- |
| Success | 0.683 (0.667 to 0.700) | 0.689 (0.667 to 0.700) | 0.694 (0.667 to 0.717) |
| Execution accuracy | 0.433 (0.425 to 0.450) | 0.525 | 0.633 (0.625 to 0.650) |
| Wrong-answer rate | 0.038 (0.037 to 0.038) | 0.012 (0.000 to 0.037) | 0.083 (0.069 to 0.107) |
| Abstention precision | 0.610 (0.591 to 0.619) | 0.544 (0.542 to 0.545) | 0.568 (0.522 to 0.591) |
| Abstention recall | 1.000 | 0.949 (0.923 to 1.000) | 0.974 (0.923 to 1.000) |
| Latency p50 (s) | 6.9 (6.7 to 7.1) | 6.7 (6.4 to 6.9) | 6.0 (5.8 to 6.5) |
| Latency p95 (s) | 13.0 (10.5 to 17.1) | 11.9 (10.4 to 13.6) | 10.0 (9.5 to 10.5) |
| Cost per answer (USD, est.) | 0.0269 (0.0261 to 0.0280) | 0.0296 (0.0295 to 0.0297) | 0.0190 (0.0155 to 0.0229) |
| Model calls per answer | 8.75 (8.59 to 8.96) | 8.56 (8.48 to 8.63) | 6.05 (5.93 to 6.25) |
| Runs x questions | 3 x 60 | 3 x 60 | 3 x 60 |
| Run-to-run instability | 0.050 | 0.083 | 0.083 |

Success by expected action (all runs pooled; cases in brackets).

| Expected action | v0 | v1 | v2 |
| --- | --- | --- | --- |
| answer | 0.642 (120) | 0.667 (120) | 0.650 (120) |
| clarify | 0.444 (18) | 0.278 (18) | 0.278 (18) |
| decline | 1.000 (21) | 1.000 (21) | 1.000 (21) |
| describe | 0.667 (12) | 0.750 (12) | 1.000 (12) |
| search | 1.000 (9) | 1.000 (9) | 1.000 (9) |
