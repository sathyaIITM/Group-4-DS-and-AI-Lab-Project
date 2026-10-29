# Changelog

Entries follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions track the evaluation ladder: `v0` baseline through `v6` retraining and
recalibration, as defined in [docs/Milestone1_Report.md](docs/Milestone1_Report.md).

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

- Milestone 2 (29 October 2026): report `docs/Milestone2_Report.md` with document change
  log, contribution log and sign-off; five cleaned tables (IMD rainfall, PLFS, NFHS-5,
  Mandi, NCRB); EDA (`scripts/eda_tables.py`, `docs/figures/milestone2/`); data manifest
  with SHA-256 (`data/MANIFEST.md`); routing splits v1 tracked under `data/splits/kev/`;
  text-to-SQL reference pairs split by template into dev (63) and test (37).

### Changed

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
