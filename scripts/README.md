# Data preparation

One engine prepares every table. A table-specific choice lives in its config file, not in
code: `configs/sources/<dataset>.toml`. The output follows the data contract
(`docs/data_contract_v1.md`).

## Run it

From the repository root:

```bash
python scripts/download_raw.py            # NFHS-5 and Mandi into data/raw (needs DATA_GOV_IN_API_KEY)
python scripts/run_pipeline.py            # every table in configs/sources
python scripts/run_pipeline.py --dataset mandi_daily_prices
python scripts/run_pipeline.py --verify   # recompute catalogue facts from the files
python scripts/build_manifest.py          # checksums, config version and code commit
pytest -q
```

`python scripts/preprocess_data.py` still works; it calls `run_pipeline.py`.

What a run does, per table: reads the raw file; compares its headers with the approved
snapshot; parses and checks every value; writes `outputs/review/<dataset>.csv`; and, if
nothing blocks, publishes the files listed in the data contract. If something blocks, the
last good version stays live and the exit code is 2. A second run on an unchanged file
and config says "unchanged".

## When a run is blocked

Open `outputs/review/<dataset>.csv`. Each row has a severity, what was found, a count and a
suggested change.

| Severity | Meaning | You |
| --- | --- | --- |
| `block` | The table is not published | Fix the config or the reference files, or confirm the source changed; then rerun |
| `warn` | Published; a person should look | Confirm the values, or change a check bound |
| `info` | Published; expected | Nothing |

Common blocks and the usual fix:

| `kind` | Usual fix |
| --- | --- |
| `column_missing`, `column_dropped`, `column_added` | Update `[columns]` or `[values]` in the config, then `--approve` |
| `unparsed_token` | Add the token to `read.missing_markers` with its flag, or register a source rule |
| `unparsed_period` | Update `period.date_format` or `values.pattern` |
| `geo_unmatched` | Add a row to `configs/reference/place_aliases.csv` (States) or `subdivision_aliases.csv` (IMD sub-divisions). Case and spacing are ignored already. A name that is a different area (for example a State together with another) needs its own entry, not an alias |
| `duplicate_key` | Find the repeated rows in the source |
| `unit_change_suspected` | Check the unit in the source; set it in the config |
| `period_convention_unknown` | State `period.start_month` in the config |
| `period_overlap` | Two year windows are mixed: declare the change in `period.conventions`; state a transition year in `period.exceptions` |
| `period_redated`, `period_relabelled`, `values_revised`, `rows_removed`, `indicators_removed`, `unit_changed`, `period_type_changed`, `category_columns_changed` | The new file differs from the live release (next section) |

`python scripts/run_pipeline.py --approve` stores the header snapshot and profile of a run
that you have reviewed (`configs/profiles/`). Later runs are compared with them.

## When the source changes

Each run is also compared with the live release of the same dataset (`data/processed/`). The
differences are in `outputs/review/<dataset>.csv`. Read them against the publisher's note.

- If the publisher moved the start of the year for new years only, add
  `[[period.conventions]]` with `from_year` and `start_month`. If the move leaves a transition
  year, state its dates in `[[period.exceptions]]`. Earlier years keep their old window.
- To release a change that you have checked (a corrected source, a rolling window, a new
  definition), run
  `python scripts/run_pipeline.py --dataset <id> --accept-changes "<reason>"`. The reason is
  written to `outputs/lineage/<id>.json`. Only the comparison findings can be accepted this
  way; a duplicate key or an unparsed value cannot.
- Set `period.verified_through` to the last start year whose window you confirmed with the
  publisher. Later years are published with a warning until you raise it.
- Set `period.expect_contiguous = true` for a source that should be daily; months and seasons
  are checked for a missing year in each slot automatically.

## Adding a table

1. Put the raw file in `data/raw/`.
2. Copy the config of the most similar table in `configs/sources/` and change it. The
   sections are explained by the comments in the existing files.
3. Run the pipeline and read `outputs/review/<dataset>.csv`.
4. Resolve every `block`; run with `--approve`; commit the config and the snapshot.

A source-specific rule (code) is allowed only when a defect cannot be expressed in the
config. It goes in `src/analyst/data/source_rules.py` with its evidence and a test. The only
one today is `nfhs5_minus_as_low_sample`.

## Rebuild-equality tests

`tests/test_rebuild.py` compares the rebuilt tables with the Milestone 2 outputs in
`data/processed/golden_v1/` (not tracked; their checksums are asserted in the test). To
recreate them, check out commit `7f58bed`, run the Milestone 2 script
(`python scripts/preprocess_data.py` and the IMD/PLFS loader) and copy the five Parquet files
into that folder. The tests are skipped when the raw files or the golden folder are absent;
every other test runs on a clean clone.

## Other scripts

| Script | Purpose |
| --- | --- |
| `download_raw.py` | Download the raw files from the data.gov.in API |
| `eda_tables.py` | Exploratory analysis and figures into `docs/figures/milestone2/` |
| `split_ground_truth.py` | Split the reference pairs into dev and test by template |
| `build_manifest.py` | Write `data/MANIFEST.md` |
| `robustness_sweep.py` | Apply 13 kinds of change to each real raw file and report how the pipeline reacted (needs the raw files and a release) |

NCRB (`datafile3.csv`) comes from the catalogue download, not the API.

## Code map

| Path | Role |
| --- | --- |
| `src/analyst/data/contract.py` | Flags, column lists, review-item and catalogue models |
| `src/analyst/data/config.py` | The config schema |
| `src/analyst/data/ops.py` | Generic operations (text, numbers, dates, places, units) |
| `src/analyst/data/source_rules.py` | Registry of source-specific rules |
| `src/analyst/data/engine.py` | Raw file plus config to the observation table and review items |
| `src/analyst/data/validate.py` | Pandera schema built from the config |
| `src/analyst/data/views.py` | Agent table from the observation table |
| `src/analyst/data/profile.py` | Profiles and drift comparison |
| `src/analyst/data/periods.py` | Overlapping and absent periods; years later than the confirmed one |
| `src/analyst/data/reconcile.py` | Comparison of a new release with the live one; accepted changes |
| `src/analyst/data/publish.py` | Staging, catalogue, lineage, release check |
