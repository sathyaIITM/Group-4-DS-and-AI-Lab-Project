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

### Notes

- No model, agent or tool code is implemented yet. Milestone 2 (29 October
  2026) freezes the table list and delivers the first cleaned tables and
  catalogue.
