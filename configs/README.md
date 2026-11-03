# Configuration

One file per concern, loaded through `pydantic-settings`. Values that are
secrets come from the environment, never from these files; `.env.example` lists
the variable names.

Expected files, added as the corresponding component lands:

| File | Purpose |
| --- | --- |
| `catalogue.toml` | The table list, with source, version and licence per table, plus the metadata the Kev data generator samples from (draft; frozen in Milestone 2). TOML because the standard library reads it. |
| `sources/<dataset>.toml` | One file per prepared table: how it is read, what its rows and columns mean, its year and place conventions, its checks and its agent table. Read by the data pipeline (`scripts/README.md`) |
| `profiles/<dataset>.{columns,profile}.json` | Approved header snapshot and value profile of each table; later runs are compared with them |
| `reference/` | Canonical State and UT names, place aliases (`place_aliases.csv`), IMD sub-division names and their aliases (`subdivision_aliases.csv`) |
| `model.yaml` | Hosted LLM and decision-model identifiers (Kev, Jev), by operating mode |
| `train.yaml` | Kev fine-tuning runs: base checkpoint, LoRA rank, epochs, learning rate, data file |
| `inference.yaml` | Decision-layer backend chain, confidence bands and per-decision gate margins |
| `evaluation.yaml` | Experiment definitions E1–E7 and the objective targets O1–O8 |
| `prompts/` | Prompt templates, including the versions produced by DSPy and GEPA |

Record the provider, model identifier and access date with every reported
result. A backend or version change requires recalibration and a re-run of the
affected rows.

## Optional fields of `sources/<dataset>.toml`

| Field | Use |
| --- | --- |
| `period.type = "quarter"` with `period.quarter_map` | Quarters named in a column, for example `"April-June" = { label = "Q2", start_month = 4, end_month = 6 }`; `year_offset = 1` for a fiscal quarter that falls in the next calendar year. The columns need the roles `period_year` and `period_quarter` |
| `period.conventions` | `[[period.conventions]]` with `from_year` and `start_month`: the year starts in another month from that year on |
| `period.exceptions` | `[[period.exceptions]]` with `year`, `start`, `end`: one year with stated dates (a transition year) |
| `period.verified_through` | Last start year whose window a person confirmed; later years are published with a warning |
| `period.expect_contiguous` | `true` for a daily source, `false` to switch off the check for absent periods |
| `values.pattern` | Header regex; group 1 is the start year, an optional group 2 the end-year suffix as published |
| `geo.subdivision_alias_reference` | Alias file for sub-division names (default `subdivision_aliases`) |
| `[reconcile]` | `max_revised_share` (0.10), `max_removed_share` (0.05), `value_rtol` (1e-6): how far a new release may differ from the live one before it blocks |
