# Outputs

Generated artefacts, kept separate from source code. Ignored by git by
default; the files cited as evidence in a milestone report are added
explicitly (`git add -f`) so the report's claims can be checked. Regenerate any
file with the command given in the report.

Files committed as Milestone 3 evidence (commands in Appendix A of
`docs/milestones/Milestone3_Report.md`):

| File | Report section |
| --- | --- |
| `predictions/rag_poc_flash_lite.jsonl` | 8.5, 9: end-to-end run, one record per question |
| `predictions/end_to_end_slice.jsonl` | 8.4: component slice |
| `predictions/domain_{zeroshot,train250,laya_zeroshot,jev}_{calibration,dev_synthetic}.jsonl` | 5.4, 7.5: domain predictions |
| `reports/domain_{zeroshot,train250,laya_zeroshot,jev}_score.json` | 5.4, 7.5: scores and fitted temperatures |
| `logs/domain_overfit32.log`, `logs/domain_train250.log` | 7.5: training runs |
| `logs/serve_*.log` | 7.5, 8.4: serving runs |
| `week1/routing_kev.jsonl`, `week1/routing_jev.jsonl` | 1.4: week-1 tool-selection check |

| Directory | Contents |
| --- | --- |
| `predictions/` | Model and agent outputs on dev and test questions: generated SQL, executed results, confidence scores |
| `reports/` | Generated evaluation tables: the version ladder (E1), gate comparisons (E3), ablations (E5), calibration reports |
| `figures/` | Plots: reliability diagrams, ECE by version, cost and latency charts, confusion matrices for routing decisions |
| `logs/` | Run logs: training runs, calibration fits, evaluation sweeps, Langfuse export summaries |

Each run should write to a dated subdirectory (for example
`reports/2026-11-05_e1-version-ladder/`) so results are not overwritten and can
be cited by commit and date in the milestone reports.
