# Contributing

This repository holds one DS & AI Lab course project (Generative AI track): an
analyst agent for Indian public data with calibrated decision models. The plan
of record is
[docs/Milestone1_Report.md](docs/Milestone1_Report.md). Course requirements are
set by the
[milestone schedule](https://bsc-iitm.github.io/dsai-lab-project/milestones.html)
and the
[project guidelines](https://bsc-iitm.github.io/dsai-lab-project/guidelines.html).

## Team tracks

Four tracks rotate between the team members:

| Track | Member | Roll number | Scope |
| --- | --- | --- | --- |
| T1 Data and Tools | Shaoni Samanta | 21f1003157 | Sourcing, profiling, cleaning steps, validation, catalogue, onboarding pipeline, typed tools |
| T2 Agent | Shivanshu Gupta | 22f3002985 | LangGraph workflow, resolvers, query generation, execution, evidence panel, streaming UI |
| T3 Model | Sathya Prakash | 21f1006001 | Kev fine-tuning, calibration fits, gates, retrieval, decision-model experiments |
| T4 Ops and Evaluation | Ashmit Ghose | 24f1001827 | Question–reference pairs, splits, leakage checks, experiments E1–E6, deployment, tracing, cost |

The previous owner of a track reviews the pull requests of the next owner. Every
pull request requires one approving review before merge.

## Worklog

[WORKLOG.md](WORKLOG.md) tracks individual contributions and is updated every
week, per the course guidelines. Add a row per person per week, even when a
week has no progress; link the commit, pull request or file a row refers to
rather than restating it.

## Branches

| Purpose | Pattern | Example |
| --- | --- | --- |
| New work | `feature/<track>-<name>` | `feature/t3-kev-calibration` |
| Corrections | `fix/<name>` | `fix/unit-normalisation` |
| Documentation | `docs/<name>` | `docs/milestone-2-report` |

`main` is the integration branch. Commit directly to `main` only for the initial
scaffold.

## Code standards

- Python 3.12 or 3.13. Kev's serving stack requires one of these versions.
- PEP 8, enforced by Ruff (`ruff format`, `ruff check`). Line length 100.
- Type hints on all public functions; `mypy --strict` must pass.
- Pydantic models are the contracts for tools, decisions and streamed events.
  Do not pass untyped dictionaries across those boundaries.
- Tests live in `tests/`, mirroring the package layout. Mark tests that need a
  GPU, a hosted API or more than a few seconds with the corresponding pytest
  marker.

Install the development environment and hooks:

```bash
python -m pip install -e ".[dev]"
pre-commit install
```

## Working agreements

- Ask the team before spending money or creating accounts.
- Never commit secrets or API keys. Configuration comes from the environment;
  `.env.example` lists the variable names and no values.
- Keep large data and model files out of git. Commit samples and download
  scripts only. `data/raw`, `data/processed`, `data/splits`, `models/` and
  `outputs/` are ignored; `data/sample` is tracked.
- The frozen 200-question test set is never used for training or tuning.
- Decision models are evaluated on human labels only.
- Record the provider, model identifier and access date with every reported
  result. A backend or version change requires recalibration and a re-run of
  the affected rows.

## Writing

Documents in `docs/` are formal, crisp and impersonal: no filler, contractions
or rhetorical framing. Label estimates as estimates and vendor or project
benchmarks as self-reported. Verify every citation against the source. The
retraining procedure is human-approved; describe it as a "human-approved
retraining procedure", not as a closed or self-improving loop.
