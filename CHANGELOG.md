# Changelog

Entries follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions track the evaluation ladder: `v0` baseline through `v6` retraining and
recalibration, as defined in [docs/milestones/Milestone1_Report.md](docs/milestones/Milestone1_Report.md).

## [Unreleased]

### Added

- Repository scaffold: package layout under `src/analyst`, application
  directories, configuration, infrastructure and test directories.
- Project metadata: `pyproject.toml`, `LICENSE`, `CONTRIBUTING.md`, this file.
- Docker Compose stack: `ui`, `api` (API and agent), `admin`, Postgres with
  pgvector, and Caddy.
- Milestone 1 report, architecture diagram and TA presentation deck under `docs/`.
- `WORKLOG.md`, required by the course guidelines: individual contributions,
  updated weekly.
- Repository structure and `README.md` aligned to the course guidelines
  (https://bsc-iitm.github.io/dsai-lab-project/guidelines.html): `outputs/`
  and `models/` subfolders, named test stubs, README sections for features,
  dataset, models, results, demo and team members.

- Milestone 2 (29 October 2026): report `docs/milestones/Milestone2_Report.md` with document change
  log, contribution log and sign-off; five cleaned tables (IMD rainfall, PLFS, NFHS-5,
  Mandi, NCRB); EDA (`scripts/eda_tables.py`, `docs/milestones/figures/milestone2/`); data manifest
  with SHA-256 (`data/MANIFEST.md`); routing splits v1 tracked under `data/splits/kev/`;
  text-to-SQL reference pairs split by template into dev (63) and test (37).

- Reusable data preparation (3 November 2026, Milestone 2 resubmission): one pipeline driven by
  a config per table (`configs/sources/`) in place of per-table scripts; shared observation
  tables (`obs_<dataset>`) with a quality flag, original text and rule ids on every value for
  all five datasets; review list and suggested fixes instead of silent corrections; approved
  header snapshots and drift checks; generated `catalogue.json` and `dim_period`; lineage log
  and manifest with raw checksum, config version and code commit; fault-injection and
  rebuild-equality tests (`tests/`). Specification in `docs/specs/data_contract_v1.md`.
- Handling of changes in public data (3 November 2026, contract 1.1): year windows that change
  over time (`period.conventions`, `period.exceptions`, `period.verified_through`), overlap and
  gap checks on periods, a `quarter` period type, comparison of each release with the live one
  of the same dataset with accepted changes recorded in the lineage, place names matched
  ignoring case and spacing, sub-division aliases, single-year period headers, a warning for
  checks that name a missing column, and `scripts/robustness_sweep.py`.
- Candidate tables (5 November 2026, T1): source record `docs/specs/candidate_tables.md` for the ten
  T1 tables and the four `data_discovery` files (resource ids, publishers, periods, units, place
  spellings, quirks, decisions); `scripts/download_raw.py` covers the ten tables and accepts file
  names to download only those; raw-file list in `data/README.md`.
- Agent design, base version (T2 and T4): `docs/Langgraph diagram.md`, the node graph from which
  `docs/specs/agent_graph.md` version 0.1 was derived.
- Milestone 3 (5 November 2026): report `docs/milestones/Milestone3_Report.md` and slides
  `docs/milestones/Milestone3_TA_Presentation.pptx`; agent graph specification
  `docs/specs/agent_graph.md` (version 0.3); phase 1 of the Kev adoption, the domain decision:
  `src/analyst/decisions/phase1.py`, `scripts/build_domain_phase1.py`,
  `src/analyst/evaluation/domain_eval.py` (temperature fit, paired bootstrap),
  `scripts/domain_phase1_eval.sh`, choice-question support in `system_one.py`; an end-to-end
  slice over the five tables, `src/analyst/pipelines/end_to_end_slice.py`; tests
  `tests/test_domain_phase.py` and `tests/test_end_to_end_slice.py`.
- Jev zero-shot reference on the domain decision (5 November 2026): accuracy 0.929 on the 338
  dev-synthetic items (`outputs/reports/domain_jev_score.json`, not tracked).

### Changed

- `.gitignore` (5 November 2026): exception for `configs/reference/*.csv`, which the data
  pipeline and 55 tests need and which were not tracked.
- Data preparation (3 November 2026): IMD and PLFS now carry `quality_flag` and `rule_ids`;
  place names the old alias list left unstandardised (`Maharastra`, `Jammu & Kashmir`,
  `Dadra and Nagar Haveli & Daman and Diu`, `Chattisgarh`, `Andaman and Nicobar`) are now
  standardised in `state_name`, source spellings kept; quality flags use one shared
  vocabulary (`missing_or_unparseable` is `unparsed`, `invalid_price_order` is `inconsistent`,
  `passed` is `reported`). Reference queries `Q025` and `Q059` use the new flag names; all
  90 executable reference queries return the same results as before.
- Preprocessing script runs from any directory; NFHS-5 cells exported as negative numbers
  are read as low-sample estimates; Mandi rows with implausible prices are flagged.
- Reference queries `Q012` and `Q019` corrected to match the prepared NFHS-5 labels.
- Milestone 1 report revised (27 October 2026) in response to TA feedback:
  - Refined the problem statement, research questions and project scope.
  - Strengthened the literature review; clarified research gaps and the proposed contribution.
  - Clarified the system architecture, decision-model roles and baseline comparisons.
  - Defined end-to-end correctness, confidence calibration, evaluation metrics and abstention criteria.
  - Added a failure taxonomy distinguishing data limitations from system errors.
  - Expanded the evaluation plan, dataset requirements, feasibility checks, risks and Milestone 2 deliverables.
  - Verified by 
    - Shivanshu Gupta (22f3002985), 27 October 2026.
    - Sathya Prakash (21f1006001), 27 October 2026.

### Notes

- No model, agent or tool code is implemented yet. Milestone 2 (29 October
  2026) freezes the table list and delivers the first cleaned tables and
  catalogue.
