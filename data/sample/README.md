# Sample extracts

Small, committed extracts of the cleaned tables, used by tests and reviews so
that neither requires a download. Keep each file well under a megabyte and
record the source table and version in its header or in this file.

The table list is frozen in Milestone 2. The files below belong to the week-1
feasibility checks (branch `feature/week1-feasibility`) and are not the frozen
catalogue.

## Source tables (week 1)

Both are published on the Open Government Data Platform India under the
Government Open Data License - India. Raw files and Parquet conversions are
not committed (`data/raw/`, `data/processed/`); regenerate them with
`analyst.data.ogd.fetch_resource` (needs `DATA_GOV_IN_API_KEY`) and
`analyst.data.loaders.build_parquet`.

| Table | Publisher | data.gov.in resource id | Retrieved | Rows |
| --- | --- | --- | --- | --- |
| `imd_subdivision_monthly_rainfall`: sub-divisional monthly rainfall, 1901-2017 (mm) | India Meteorological Department, Ministry of Earth Sciences | `8e0bd482-4aba-4d99-9cb9-ff124f6f1c2f` (catalogue entry `fb5e2a33-3e34-4087-83a1-f0e46f2748d0`) | 2026-10-23 | 4,188 |
| `plfs_state_ur_usual_status`: state-wise unemployment rate, usual status (ps+ss), persons 15+, 2017-18 to 2021-22 (percent) | Rajya Sabha answer table citing MoSPI (PLFS) | `d038e512-231e-4adb-bbb7-a3f95102d18a` | 2026-10-23 | 38 |

Known features kept on purpose: IMD sub-divisions rather than states (names
such as `Orissa`); PLFS years as columns, `NA` strings, an `All India` row and
`Odisha`; calendar years in one table and July-June survey years in the other.
A near-duplicate PLFS resource (`89e6c4b7-4c56-4f4c-b196-a40726ebd7fe`) and an
all-ages variant (`302a4e58-b2e0-46c8-a40e-154392a9c5d9`) exist in the same catalogue.

## Evaluation inputs (week 1)

| File | Content | Status |
| --- | --- | --- |
| `routing_week1.jsonl` | 200 tool-selection examples (6 tools: `search_catalog` 27, `describe_table` 28, `run_sql` 45, `make_chart` 30, `ask_clarification` 38, `decline_not_covered` 32). Fields: `question`, `has_result`, `prior_turn`, `label`. | Labels are teacher-written (`label_source: teacher`) and **not yet human-checked** (`human_checked: false`). A feasibility signal only until checked. |
| `v0_questions.jsonl` | 20 questions with DuckDB reference SQL and reference answers (18 answerable, 2 to be declined). | Reference answers re-executed against the Parquet tables; the choices flagged in each `note` are assumptions. |
