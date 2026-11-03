# Data contract, version 1.1

The pipeline publishes every dataset in one fixed shape. Code that reads data (the agent,
the routing-data generator, the evaluation sets) depends on this shape only, never on how
a table was produced. A change to the shape is a new contract version.

Version 1.1 is additive. It adds the period type `quarter`, the catalogue field
`period_conventions` and release rules 8 and 9. Tables built under 1.0 remain valid.

## What is published

For each dataset `<d>` in `configs/sources/`:

| File in `data/processed/` | What it is | Who reads it |
| --- | --- | --- |
| `obs_<d>.parquet` | **The contract table.** One row per value, with a quality flag on every value | New code; tests; anything that needs flags |
| `<d>.parquet` | **Agent table.** The same values in the shape used since Milestone 2 (IMD and PLFS wide by period, Mandi and NCRB one row per record, NFHS-5 long), plus `quality_flag` and `rule_ids`. Generated from `obs_<d>` by the `[view]` section of the config | The 100 reference queries; the v0 baseline; the prompts |
| `<d>_quality_report.csv` | Row count and count of each flag | People |
| `catalogue.json` | Facts about every table, **recomputed from the data** on each release | Agent, generator, labelling rules |
| `dim_period.parquet` | One row per day with its calendar, fiscal (April-March) and July-June year | Queries that change the year type |

The agent table keeps its Milestone 2 name so that nothing already written breaks. The
design calls it a view (`v_<d>`); in this milestone it is a file. Moving the agent to
`obs_<d>` is a Milestone 3 decision.

## The observation table `obs_<d>`

One row = one value. Read the columns in groups.

| Group | Columns | Meaning |
| --- | --- | --- |
| Which table | `dataset_id`, `dataset_version` | Version is `<config version>+<first 8 characters of the raw file checksum>` |
| Which source row | `source_row` | Row number in the raw file. Lets you trace a value back |
| Place | `geo_level`, `geo_code`, `geo_name`, `geo_name_source`, `geo_state`, `geo_state_source`, `geo_district`, `geo_district_source`, `geo_vintage`, `geo_match`, `is_total_row` | `geo_name` is the clean name, `*_source` is the name as published. `geo_match` is `exact`, `alias` (matched through the alias table, or equal to a listed name ignoring case and spacing) or `unmatched`. `geo_vintage` says which boundaries the source used. `is_total_row` marks rows such as "All India" |
| Period | `period_type`, `period_label`, `period_source`, `period_start`, `period_end` | Always filter on the two dates, never on the label. `period_type` is `date`, `month`, `quarter`, `season`, `calendar_year`, `survey_year` or `survey_round` |
| Measure | `indicator_id`, `indicator_label_source` | What is measured |
| Categories and details | Dataset-specific, for example `commodity_name`, `variety`, `grade` (Mandi) and `sample_households` (NFHS-5) | Categories identify a value; details only describe it |
| Value | `value`, `unit`, `value_raw` | Clean number, standard unit, original text |
| Quality | `quality_flag`, `rule_ids`, `checks_failed` | See below |

`geo_code` is a project code such as `state:odisha` or `district:odisha/khordha`. Official LGD
codes replace it when the place tables are added (planned for the week of 4 November).

### Quality flags

Every value has exactly one flag. When several apply, the one highest in this table wins.

| Flag | Meaning | `value` |
| --- | --- | --- |
| `unparsed` | Text the config does not recognise. Never guessed | empty |
| `missing_in_source` | The source shows a missing-value marker (`NA`, empty) | empty |
| `suppressed` | The publisher withheld the value (NFHS-5 `*`) | empty |
| `out_of_range` | Outside the allowed range (for example a negative rainfall) | kept |
| `inconsistent` | Breaks an order or sum rule (min above modal; total not equal to parts) | kept |
| `implausible` | In range but outside the believable band (Mandi) | kept |
| `low_sample_estimate` | Published with a caveat: few survey cases | kept |
| `revised`, `provisional` | The source says so (not used by the current five tables) | kept |
| `reported` | Published value; all checks passed | kept |

`value` is empty exactly when the flag is `unparsed`, `missing_in_source` or `suppressed`.
`rule_ids` lists every rule that touched the value, for example `marker:*` or
`nfhs5_minus_as_low_sample`. `checks_failed` lists the declared checks the value failed.

## Rules every release must pass

A table that breaks one of these is not published; the last good version stays live.

1. No two rows share the key (place, period type, period, indicator, categories).
2. Every value has a unit, a flag and its original text; `value` is empty only for the three flags above.
3. `period_start` is not after `period_end`; a missing period is allowed only for `unparsed` values.
4. Flags, `geo_match` and `period_type` use the closed lists in this document.
5. Declared sum and order rules hold, or the values are flagged `inconsistent`.
6. Every fact in `catalogue.json` equals the same fact recomputed from the published file (`python scripts/run_pipeline.py --verify`).
7. Running the release again gives the same checksums.
8. No two periods of one type overlap within a series (same place, indicator and categories). A year
   window that changed over time is declared in `period.conventions` and `period.exceptions`.
9. Compared with the live release of the same dataset, a table that re-dates or relabels periods
   already published, revises more than 10% of the shared values, loses more than 5% of its
   observations, drops an indicator or changes a unit is not published until a person accepts the
   change with a stated reason (`--accept-changes`). The reason is kept in the lineage record.

## Changes in the source

Public data changes without notice. These checks make a change visible; none corrects a value.

| Change | Seen by | Result |
| --- | --- | --- |
| A year starts in another month | Overlap of two periods of one series; comparison with the live release (`period_redated`) | Block |
| A window that changed from a known year | `period.conventions` and `period.exceptions` in the config | Both windows kept |
| Periods later than the last year a person confirmed | `period.verified_through` | Warn |
| A period absent between two that are present | Gap check (consecutive years and quarters; same slot every year for months and seasons) | Warn |
| Earlier values change | Comparison with the live release | Warn, or block above 10% of shared values |
| Periods renamed with the same dates | Comparison with the live release (`period_relabelled`) | Block |
| Years dropped, indicators lost, units changed | Comparison with the live release | Warn or block |
| New places, categories or indicators | Comparison with the live release | Info |
| A check names a column that does not exist | Check targets | Warn |

The comparison needs a live release in `data/processed/` and therefore works per machine. It
compares a dataset with its own earlier release, not with other datasets.

## Using it

```sql
-- the latest published period, with its dates, for one indicator
SELECT geo_name, period_label, period_start, period_end, value, unit, quality_flag
FROM obs_plfs_state_ur_usual_status
WHERE indicator_id = 'ur_usual_ps_ss'
  AND period_end = (SELECT MAX(period_end) FROM obs_plfs_state_ur_usual_status)
  AND NOT is_total_row
ORDER BY value DESC;
```

Always report any flag other than `reported` with the figure. Never add or average values
of an indicator whose unit is `percent` or a rate across places.

## What is not in version 1

- Official LGD place codes, `geo_alias` and `geo_lineage` tables (planned).
- Domain-level configuration files; plausibility bands live in each table's `[[checks]]`.
- Comparison of two different datasets that publish the same statistic (for example two IMD files
  with different values for the same sub-division and month). Each dataset is compared only with
  its own earlier release.
- A publisher's change to the year window for new periods only, with unchanged labels, is seen
  only as `year_window_unverified` (when `verified_through` is set), not as a data change.
- The language-model drafting of configs (described as a possible extension).

See `scripts/README.md` for how to run the pipeline and `configs/sources/` for the
configuration of each table.
