# Notebooks

Exploration and profiling only. Anything the pipeline depends on moves into
`src/analyst` with tests. Clear outputs before committing, and keep data
paths relative to `data/`.

Numbered by stage, one notebook per stage:

| Notebook | Stage |
| --- | --- |
| `01_EDA.ipynb` | Exploratory analysis of the candidate and frozen tables |
| `02_Preprocessing.ipynb` | Cleaning steps, comparability checks, catalogue construction |
| `03_Model_Experiments.ipynb` | Kev fine-tuning runs, calibration fits, retrieval experiments |
| `04_Evaluation.ipynb` | Version-ladder and ablation runs (E1–E6), result tables |

None exist yet; the catalogue and its EDA land in Milestone 2.

Fine-tuning runs on a Colab T4 (about 15 GB, fp16 only — the T4 does not
support bf16). Keep a copy of each training notebook here with its outputs
cleared, and record the run configuration in `outputs/`.
