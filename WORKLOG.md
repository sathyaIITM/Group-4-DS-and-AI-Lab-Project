# Worklog

Individual contributions, updated weekly, per the course guidelines
(https://bsc-iitm.github.io/dsai-lab-project/guidelines.html and
https://bsc-iitm.github.io/dsai-lab-project/milestones.html). One row per
person per week; link the commit, pull request or document a row refers to
rather than restating its content.

Team tracks and members are defined in [CONTRIBUTING.md](CONTRIBUTING.md):
T1 Data and Tools (Shaoni Samanta, 21f1003157), T2 Agent (Shivanshu Gupta,
22f3002985), T3 Model (Sathya Prakash, 21f1006001), T4 Ops and Evaluation
(Ashmit Ghose, 24f1001827).

| Week ending | Member | Track | Work completed | Link |
| --- | --- | --- | --- | --- |
| 2026-10-22 | Team (all) | T1/T4 | Repository scaffold (package layout, Compose stack, configs, CI-ready lint/type/test setup); Milestone 1 report content finalised and aligned to the course guidelines; `.gitignore`, `CONTRIBUTING.md`, `CHANGELOG.md` | this repository, initial commit range |
| 2026-10-29 | Sathya Prakash | T3 (with T1/T4 checks run on this branch) | Week-1 feasibility: two tables downloaded from data.gov.in and converted to Parquet; 200 routing examples and 20 v0 questions (labels unchecked); Kev-0.8B zero-shot vs Jev routing evaluation (0.42 vs 0.815, preliminary); read-only SQL runner and v0 harness (no LLM key yet, not run); Compose + Caddy SSE check with Caddyfile fixes; Kev fine-tune dry run on MPS | branch `feature/week1-feasibility`, [docs/week1-feasibility.md](docs/internal_reports/week1-feasibility.md) |
| 2026-10-29 | Sathya Prakash | T3 50% / T1 50% (data preparation for model tuning) | Kev model-tuning data, first pass: labelling guide v1.0-draft (16 tool rules, 8 domain rules; all open questions H1-H11b decided); Kev record contract with fixed question text; draft catalogue config; rule-based generator with minimal pairs and group-merged splits; checks (balance, length, leakage, duplicates, keyword baseline). 2,356 rule-labelled records (train 1,718, calibration 300, dev-synthetic 338; guide 1.0-draft.4), validated with Kev's loader, **not yet human-checked**. Model-written data ingested on 2026-10-24 (609 paraphrases, 398 hard cases, 200 double-relabelled items, 40 red-team items) and kept apart as unreviewed candidates (`src/analyst/data/kev_ingest.py`); guide amended to draft 5 (proposed, unconfirmed); critic step prepared; evaluation-only sets (golden, dev-human, held-out-table) are out of this scope. | [docs/labelling_guide_v1.md](docs/labelling_guide_v1.md), `src/analyst/data/kev_generate.py`, `src/analyst/data/kev_checks.py`, `src/analyst/decisions/kev_questions.py`, `configs/catalogue.toml` |

## How to fill this in

- Add a row per person, per week, even for a week with no progress (state
  "no progress" and why — blocked, exam clash, reassigned).
- Keep entries to one or two lines: what was done, not how it felt to do it.
- Link to the evidence (a commit range, a PR, a file added, a notebook run) so
  a reviewer can verify the row without asking.
- Do not delete past rows; this file is the project's contribution record for
  the full six milestones.
