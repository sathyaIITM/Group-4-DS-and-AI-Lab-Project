# Outputs

Generated artefacts, kept separate from source code. Not tracked by git except
this file and the `.gitkeep` placeholders; regenerate by re-running the
relevant pipeline or notebook.

| Directory | Contents |
| --- | --- |
| `predictions/` | Model and agent outputs on dev and test questions: generated SQL, executed results, confidence scores |
| `reports/` | Generated evaluation tables: the version ladder (E1), gate comparisons (E3), ablations (E5), calibration reports |
| `figures/` | Plots: reliability diagrams, ECE by version, cost and latency charts, confusion matrices for routing decisions |
| `logs/` | Run logs: training runs, calibration fits, evaluation sweeps, Langfuse export summaries |

Each run should write to a dated subdirectory (for example
`reports/2026-11-05_e1-version-ladder/`) so results are not overwritten and can
be cited by commit and date in the milestone reports.
