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
| `reference/` | Canonical State and UT names, place aliases (`place_aliases.csv`), IMD sub-division names with their States (`imd_subdivisions.csv`) and aliases (`subdivision_aliases.csv`), district names shared by two States (`duplicate_districts.csv`). See "Place reference files" below |
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

## Place reference files (Milestone 5)

Used by the agent's place resolution (`src/analyst/tools/places.py`); checked by
`tests/test_reference_places.py` and `tests/test_data.py`.

| File | Columns | Content and source |
| --- | --- | --- |
| `imd_subdivisions.csv` | `subdivision`, `states`, `source` | The 36 IMD sub-divisions of `imd_subdivision_monthly_rainfall`, spelled as in the table (source: data.gov.in resource "Sub-divisional monthly rainfall 1901-2017"). `states` lists the States and UTs each covers, separated by `;`, spelled as in `states.csv`; this mapping follows IMD's sub-division boundaries and is not part of the source file. Judgement calls: Puducherry maps to Tamil Nadu only (most of the UT; Mahe and Yanam lie in Kerala and Coastal Andhra Pradesh); Dadra and Nagar Haveli and Daman and Diu to Gujarat Region; Ladakh to Jammu & Kashmir (the data end in 2017, before the split). `subdivision` must stay the first column: the pipeline reads only that column |
| `subdivision_aliases.csv` | `alias`, `canonical`, `evidence` | Other names of a sub-division: Odisha to Orissa (the table keeps the former name), Marathwada to Matathwada (spelling in the table), Rayalaseema to Rayalseema, the full form of Naga Mani Mizo Tripura |
| `place_aliases.csv` | `alias`, `canonical`, `evidence` | State spellings, and (Milestone 5) short names of the 32 markets with the most rows in `mandi_daily_prices` (snapshot of 29 October 2026): the stored name without "APMC", "RM", "Market" or "(Uzhavar Sandhai )", spacing variants and official or former town names. A plain name shared by several markets (Pune: APMC Pune, Pune(Moshi), Pune(Khadiki), Pune(Pimpri)) is left out, so the agent asks which market. An alias is used only when its target exists in the table queried, so market rows do not affect State tables |
| `duplicate_districts.csv` | `district`, `state`, `dataset_id` | Every district name stored with two or more States in `nfhs5_district_indicators`, `crop_production_district` and `imd_district_rainfall_normals` (8 names, 36 rows), spelled as in each table. Without a State the agent asks which district (rule S2). "Chandel" under Mizoram in the NFHS-5 district table is probably a source error for Saiha (Chandel is a Manipur district; Saiha is absent); it is listed because the table holds it |
