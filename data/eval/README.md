# e2e_v1: end-to-end evaluation set

Version 1.0, 17 November 2026. Status: **written, not yet validated** (every line has
`"validated": false`; T1 sets it to `true` after the validation described below).

## Purpose

`e2e_v1.jsonl` holds 100 questions whose outcome is fixed in advance. The end-to-end success rate of
the agent versions v0, v1 and v2 is measured on it (T1 brief, Section 6; T4 brief, Section 5). The
questions were written from the published tables and the labelling guide (v1.0) without looking at
agent output. T4's script splits the set into `e2e_dev` (40, tuning) and `e2e_test` (60, frozen); the
split is not part of this file. The `e2e_test` questions must not be pasted into prompts or reused as
verified examples.

## Mix (counts in the committed file)

| Dimension | Required | Found |
| --- | --- | --- |
| `answer` | at least 70 | 71 |
| `decline` | at least 12 | 14 |
| `clarify` | at least 8 | 8 |
| `describe` or `search` | at least 3 | 7 (4 describe, 3 search) |
| Questions per published table | 5 to 20 | 5 to 8 (table below) |
| Derived values (percentage change, percentage points, share) | at least 10 | 13 |
| Items testing a named convention | at least 15 | 52 |
| Follow-ups with `prior_turns` | at least 10 | 11 |

Operations among the 71 `answer` items: lookup 28, ranking 15, change 11, comparison 8, trend 4,
aggregate 3, share 2.

| Table (`dataset_ids`) | Items |
| --- | --- |
| `plfs_state_ur_usual_status` | 8 |
| `imd_subdivision_monthly_rainfall` | 8 |
| `cpi_all_india` | 8 |
| `mandi_daily_prices` | 7 |
| `nfhs5_district_indicators` | 7 |
| `nfhs5_state_factsheet` | 7 |
| `msp_crops` | 6 |
| `ncrb_violent_crimes_state` | 6 |
| `srs_imr_state` | 6 |
| `plfs_lfpr_urban_state` | 5 |
| `imd_district_rainfall_normals` | 5 |
| `ncrb_annual_crime_statistics` | 5 |
| `gsdp_per_capita_state` | 5 |
| `crop_production_district` | 5 |

`decline` items carry no dataset id, so they are not counted per table. Counts per convention tag
are in `outputs/reports/e2e_v1_check.json`.

## Format

One JSON object per line, with the fields of the T1 brief, Section 6, and one addition
(`derivation`):

| Field | Meaning |
| --- | --- |
| `id`, `question` | `e2e-001` to `e2e-100`; the question as a journalist would ask it, including typos, Hinglish place names and bare years |
| `prior_turns` | The earlier user questions of the conversation, oldest first; empty unless the item is a follow-up. The harness replays them before the item |
| `expected_action` | `answer`, `decline`, `clarify`, `describe` or `search` |
| `dataset_ids` | Tables the correct response uses; empty for `decline`, and for a `search` that finds nothing |
| `gold_sql` | Read-only SQL on the `obs_<dataset>` tables; `null` unless the action is `answer` |
| `expected_values` | Numbers a correct answer states. Taken from executing `gold_sql`, never typed from memory |
| `expected_entities` | Place, crop or sector names a correct answer names (the `entity` column of the gold result) |
| `tolerance` | Relative tolerance. 0.005 for values read from the table, 0.05 for derived values |
| `derivation` | `null`, or how the expected value is computed from the `value` cells of the gold rows, in row order: `difference` (last minus first), `pct_change` ((last - first) / first x 100), `share_pct` (first / second x 100). The SQL returns the input rows; the derivation is never done in SQL |
| `operation`, `conventions` | Operation of the question; tags of the conventions it tests |
| `expected_caveats`, `notes` | Caveats a correct answer states; the formula, the missing slot (`clarify`), what is missing (`decline`) or the expected content (`describe`, `search`) |
| `author`, `validated`, `written_on` | `T1`; `false` until T1 validates; `2026-11-17` |

Rules applied when writing the gold SQL: filters on `period_start` and `period_end` (never on
labels), `NOT is_total_row` where places are ranked, `quality_flag` stated or filtered, survey years
(July-June) kept apart from calendar years, fiscal years (April-March) from crop years. The
`clarify` and `decline` labels follow labelling guide v1.0: a named group or definition the table
lacks (youth, rural in an urban-only table) is a `clarify` item (R12), not a `decline`.

## How the set was verified

1. `python scripts/check_e2e_set.py` (needs `data/processed/obs_*.parquet`, which are not in git).
   It checks the JSON shape and unique ids, the action rules, the quotas above and every gold query:
   each runs through the read-only guard (`ReadOnlyDatabase`), reads only its own tables, and returns
   the expected values and entities within `tolerance`. Result: 100 items, 0 errors
   (`outputs/reports/e2e_v1_check.json`; the directory is git-ignored, so add the file with
   `git add -f` if it is cited).
2. `tests/test_e2e_set.py` runs the same check on the committed file when the tables are present, and
   shows that a wrong expected value, a table outside `dataset_ids` and a data-changing statement are
   reported.
3. Overlap: `scripts/check_dev_human_overlap.py` (character 5-gram Jaccard) against the 200
   `dev_human` items, `data/sample/*.jsonl`, `data/ground_truths/*.csv` and the verified examples
   v1 of the knowledge store: 0 items flagged at 0.8.
4. Tables used: the build of 17 November 2026 (NFHS-5 State v1.1.2 with the new indicator ids;
   rainfall normals with 641 districts; crop production with crop years 1997-98 to 2015-16).

## Validation by T1 (pending)

T1 reviews every item against the publisher's table or the source page, and in particular the
judgement items below, then sets `validated` to `true`. T4's harness re-executes the gold SQL and
returns any mismatch to T1. T3 reviews 20 random items against the labelling guide.

Items whose expected value or label rests on a judgement:

| Id | Judgement |
| --- | --- |
| e2e-023 | Two source district names are truncated (`EAST KHASI HI`, `DAKSHIN KANDA`); entity matching needs review |
| e2e-039, e2e-041, e2e-043 | The mandi feed is a one-day snapshot (29 October 2026); "right now" is read as that day; implausible values are excluded |
| e2e-070 | MSP ranking over commodity and variety rows as published; copra is fixed per calendar year and leads |
| e2e-073 | Cotton MSP without a variety is a `clarify` item; a default (medium staple) is the alternative |
| e2e-079, e2e-092 | A value that is missing in the source (Ladakh) or suppressed (Chandigarh infant mortality) is labelled `answer` with no expected value: the answer says the value is not published and gives no figure (design Section 4.5). Changed from `decline` on 18 November 2026 (T3) |
| e2e-095 | The infant-mortality search lists the SRS table and both NFHS-5 tables, although the district table holds no infant-mortality indicator |
| e2e-098 | A State wheat total as the sum of 22 district figures; the table publishes districts only |
| e2e-099 | Cotton is published in bales of 170 kg; no conversion to tonnes is applied |
| e2e-007, e2e-013 | R12 (named group absent) is labelled `clarify`; the T1 brief mentions a missing sex breakdown as a `decline` example |

## Limits

- The set covers the 14 published tables as built on 17 November 2026; a rebuild that changes
  values or ids needs a rerun of the checker.
- The tolerance is relative. T4's default (0.5% or the published precision) is stricter than
  0.05 for derived values; the harness may tighten it.
