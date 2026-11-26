# e2e_v1: end-to-end evaluation set

Version 1.0, 17 November 2026. Status: **written, not yet validated** (every line has
`"validated": false`). Milestone 5 (24-25 November 2026) validates every item against the
expected-action rules (version 2) below and adds the structured gold fields.

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

Fields added in Milestone 5 (used by scorer v3):

| Field | Meaning |
| --- | --- |
| `domain` | Domain of the measure asked for (labelling guide 1.0, Section 3): `labour`, `agriculture`, `rainfall`, `prices_economy`, `health`, `other`, `multiple` or `unspecified`. Filled by hand |
| `clarify_slot` | For `clarify` items: `indicator`, `category`, `place`, `period` or `geo_level` (rules S1-S4 below); otherwise `null`. Filled by hand |
| `clarify_options` | Acceptable answers to the clarifying question when they form a closed list from the table; otherwise `null`. Filled by hand |
| `expected_places` | Places of the gold rows, `{"name", "level"}` as stored (`geo_name`, `geo_level`). Filled by `scripts/fill_gold_fields.py` |
| `expected_periods` | Periods of the gold rows, `{"start", "end"}` (ISO dates). Filled by the script |
| `indicator_ids` | Indicators of the gold rows. Filled by the script |
| `unit` | Unit of the indicator in the catalogue. Filled by the script |
| `n_values` | Non-null values of the gold result before any derivation: the number of values a complete answer covers. Filled by the script |
| `gold_lineage` | `rows` when the place, period and indicator fields describe the gold rows; `inputs` when they describe the input rows of an aggregate (an average over States lists every State). Filled by the script |
| `validated_by`, `gold_version` | Validator (`T1`, `T2` or `T3`) and `2` once the item is validated against the rules below |
| `gold_changes` | One entry per change accepted in validation: `field`, `old`, `new`, `rule`, `decided_by`. Written by `scripts/apply_validation.py` from the sheets in `data/eval/validation/` |

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

## Expected-action rules, version 2 (24 November 2026)

Status: **draft for team review (25 November, 09:30).** Rules marked *proposed* are new in
Milestone 5 and take effect once the team confirms them; every other rule restates a decision
already recorded in the source named beside it.

### Why this section exists

`e2e_v1` was written on 17 November 2026 from labelling guide 1.0 and the T1 brief. Several
behaviours were fixed after that date (the decisions of 18-19 November below), and the guide's
router rules were written for the routing decision, not for the whole answer. Some expected
actions therefore no longer match the agreed design. This section is the single reference
against which every expected action, missing slot and expected value of the dev and test sets is
validated in Milestone 5.

Three principles apply throughout:

1. **The design is the reference, not the code.** Where the agent's behaviour differs from a rule
   below, the agent is wrong and the gold stays. Gold is never changed to match agent output.
2. **One rule decides each item.** A validator cites the rule id (`E1`, `E2`, ...) for every
   change. A case no rule decides is recorded as `undecided` and settled by the team; the decision
   is added here as a new rule.
3. **The four expected actions map to the agent's branches:** `answer` (query, chart or
   follow-up query; also an answer that states a value is not published), `clarify` (one
   question, one missing slot), `decline` (data absent, or not a data request), `describe` and
   `search` (catalogue branches).

### E. Expected action

Apply the rules in this order; the first that applies decides (labelling guide 1.0, Section 2.2).

| Id | Situation | Expected action | Source |
| --- | --- | --- | --- |
| E1 | Not a data request (greeting, writing or coding task, advice, opinion, a prediction of a non-statistical event), including one that names statistics but asks only for writing or code | `decline` | Guide R1, C2, C12 |
| E2 | The user asks which data exists on a topic, or which source covers it, whether or not the topic is in the catalogue | `search` | Guide R2, C3 |
| E3 | The user asks about a catalogue table (columns, units, coverage, definitions, method, list of places or years) and asks for no figure | `describe` | Guide R3, C10, H1 |
| E4 | A question about a table that is not in the catalogue: topic within the five domains, `search`; outside them, `decline` | `search` or `decline` | Guide R15, H9 |
| E5 | The measure asked for is in no catalogue table, including an absolute headcount where the table holds only rates | `decline`; the answer names what is missing and offers the nearest covered measure in words (never as a figure) | Guide R7, C5; design decision 18 |
| E6 | The period asked for is outside every table's range, or the question asks for today's or real-time conditions or a forecast ("Will it rain today?") | `decline` | Guide R8 |
| E7 | The question needs a geographic or time grain no table has (a city; monthly values from an annual table) | `decline` | Guide R9 |
| E8 | A joint analysis (compare, correlate, overlay) across tables whose periods do not overlap, or whose essential part is absent | `decline` | Guide R16, C4, C9, C11 |
| E9 | The question names a definition or population group the table lacks (youth, women, rural on an urban-only table, current weekly status) | `clarify`, slot `category`; options are the table's own definition or group | Guide R12, H5 |
| E10 | An explicit January-December or April-March period on the July-June PLFS table | `clarify`, slot `period`; options are the two survey years that overlap it | Guide R14, H11b |
| E11 | A named event without a date ("during demonetisation", "during the lockdown") | `clarify`, slot `period` | Guide C7 |
| E12 | A required detail is missing and no default in Section D applies | `clarify`, with the slot of Section S | Guide R10, M8 |
| E13 | Several independent figures, some covered and some not | `answer` for the covered part; the answer states what is not covered | Guide C4 |
| E14 | Every requested value is missing or suppressed in the source | `answer` with no figure: the answer states that the publisher did not report the value, with the reason flag. Not an abstention | Design Phase E; decision of 18 November 2026 (e2e-079, e2e-092) |
| E15 | Otherwise: a covered quantitative question with every detail present or supplied by a default | `answer` | Guide R5, R6, R11, R13 |

### D. Defaults that remove a clarifying question

When a default applies, the expected action is `answer` and the answer states the assumption.
An item whose only gap is covered by a default is never `clarify`.

| Id | Missing or loose detail | Default | Source |
| --- | --- | --- | --- |
| D1a | No period, for a single value, ranking, comparison or share | Latest period the table publishes, stated | Guide D1; implemented 18 November 2026 |
| D1b | "now", "currently", "right now", "latest", "these days", "at present" with a published statistical measure | Latest period the table publishes, stated (for the Mandi snapshot: the snapshot day). Only real-time conditions and forecasts are `decline` (E6) | Guide D1, R8; judgement e2e-039, e2e-041, e2e-043 ("right now" on the Mandi snapshot) |
| D1c | No period, for a trend or series | The full range the table publishes, stated | *Proposed* (agent practice since 18 November; e2e-072) |
| D2 | No place, where the table has a national row | All India (the national row) | Guide D2 |
| D2b | "India", "all-India", "national", "the country" | The national row (`is_total_row`) where the table has one; on a table without one, E12 (slot `place`) unless the question ranks or lists units | Guide D2; decision of 18 November 2026 |
| D3 | PLFS status or definition not named | Usual status (ps+ss) | Guide D3 |
| D4 | Age group not named | The table's group (15 and above) | Guide D4 |
| D5 | Rainfall measure not named | Annual total; "monsoon" means June-September | Guide D5, H8 |
| D6 | Place name variant | Exact renamings and spelling or alias forms map silently (Odisha to Orissa; Azadpur to APMC Azadpur); a place inside a composite sub-division maps to it and the answer states the mapping (Delhi to "Haryana Delhi & Chandigarh") | Guide D6, H7; design decision 18 (alias and spelling only, disclosed) |
| D6b | A State asked of the IMD sub-division table, when the State spans several sub-divisions (Karnataka, Maharashtra) | `answer` listing each sub-division; never averaged into a State figure | Guide R11, H6 |
| D7 | Bare calendar year on a July-June survey table | The survey year that starts in it ("2019" is 2019-20), stated | Guide D7, H11 |
| D7b | Agricultural year, fiscal year or January-December on a table with monthly columns (IMD rainfall) | `answer`, summing the months, which the answer states | Guide C8 |
| D8 | Evaluative word with a measure ("Is the jobless rate high?") | `answer` with defaults and a comparison with earlier periods | Guide D8, H10 |
| D9 | Area, sector or sex breakdown not named | The table's total (Total; Rural+Urban; Persons), stated | Decision of 18 November 2026 (`TOTAL_VALUES` in `tools/resolve.py`) |
| D10 | Only one valid option exists for a detail the question leaves open | That option, stated as an assumption; no clarifying question with a single option | *Proposed* (Milestone 4 error analysis, Section A6.4) |

### S. The missing slot of a `clarify` item

A `clarify` item has exactly one expected slot (`clarify_slot`), one of the values of
`QueryIntent.missing_slot`:

| Slot | Missing piece | Example |
| --- | --- | --- |
| `indicator` | The measure itself cannot be named from the message or context | "Top 5 please" (no earlier result) |
| `category` | A breakdown value that defines the measure: commodity, crop, variety, group, definition, area | "Mandi price in Azadpur today" (which commodity?); "youth unemployment" (E9) |
| `place` | The place, or which of several places with the same name | "Rainfall in 2015" (no national row); "Aurangabad" in a district table (Bihar or Maharashtra) |
| `period` | The period, where no default applies | E10, E11 |
| `geo_level` | Whether the user means a State or a district (or another level) when the name exists at both and the table holds both | A name that is both a State and a district in the same table |

| Id | Rule | Source |
| --- | --- | --- |
| S1 | When several details are missing, the expected slot is the first in this order: `indicator`, `category`, `place`, `period`, `geo_level`. The measure is settled before where and when (for a Mandi price, the commodity is asked before the market) | *Proposed* (Milestone 4 error analysis: e2e-044) |
| S2 | A district name shared by two States, with no State named, is slot `place`; `clarify_options` lists each district with its State. With the State named, the item is `answer` | Guide D6; *proposed* wording (Milestone 4 error analysis: e2e-031) |
| S3 | A place mention that matches no place of the table, exactly or through an alias, is slot `place` (never replaced by the nearest place). A place that exists at that level but has no rows in the table (a market absent from the day's snapshot) is `decline` with the reason | Design decision 18; *proposed* split |
| S4 | `clarify_options` is filled only when the valid answers form a closed list taken from the table (districts, survey years, varieties) | Section "Format" |

### F. Follow-ups (`prior_turns` not empty)

| Id | Rule | Source |
| --- | --- | --- |
| F1 | A follow-up inherits the earlier plan and changes only the slots it names ("And for Tamil Nadu?" keeps the measure and period) | Design Phase C (`prior_plan`) |
| F2 | A follow-up that widens the period ("for the whole decade", "since 2015") expects the whole series, every value | Guide R13; *proposed* wording |
| F3 | A follow-up that asks to compare with the earlier result expects both values | Guide R13; *proposed* wording |
| F4 | A follow-up with no earlier result that names no measure ("Do the same for Odisha") is `clarify`, slot `indicator` | Guide M8, H2 |

### V. Expected values

| Id | Rule | Source |
| --- | --- | --- |
| V1 | Expected values come from executing `gold_sql`, never from memory | Section "Format" |
| V2 | Rankings exclude total rows (`NOT is_total_row`); comparisons with India keep the national row | Design Phase C table; decision of 18 November 2026 |
| V3 | Derived values (difference, percentage change, share) are computed from the gold rows in code, tolerance 0.05 | Section "Format" |
| V4 | Values flagged `implausible` or `inconsistent` (Mandi) are excluded; `suppressed` and `low_sample` values are kept with their caveat | Design Phase C table; decision of 18 November 2026 |
| V5 | A ranking over fewer than three units, or with ties, expects a list, not a ranking | Design Phase E |
| V6 | Units are those of the table (cotton in bales of 170 kg; no conversion unless the question asks for one) | e2e-099 judgement |

### Rules added on 26 November 2026 (rule gaps found in validation)

The ground-truth audit (`data/eval/validation/alignment_audit.csv`, `alignment_test_ext.csv`)
found six cases no rule above decided. Each was settled once, as a general rule, by Sathya Prakash
(T3), Shaoni Samanta (T1) and Shivanshu Gupta (T2), and applied to every item alike
(`data/eval/validation/rule_gaps_draft.csv`). None was decided from agent output.

| Id | Rule | Gap |
| --- | --- | --- |
| E6a | A period stated relative to today ("last year", "this year") is read against the date the question is asked (for the evaluation sets, 26 November 2026). If it falls after the table's last period, the action is `decline` (E6) and the answer names the last period. "Latest", "most recent" and "now" are D1b, not relative periods | RG-1 |
| D6c | Widely used abbreviations of State and UT names (UP, MP, TN, AP, HP, WB, J&K) and misspellings with exactly one plausible match are alias forms under D6: `answer`, with the mapping stated. A mention with several plausible matches, or none, is S3 (`clarify`, slot `place`) | RG-2 |
| D6d | A region whose members are fixed by an official list (the eight North Eastern States) or by the question itself (a count that matches one common list, such as "the five southern States") maps to that list, stated; otherwise `clarify`, slot `place`, with the candidate lists as options | RG-3 |
| E9b | When the measure exists only for sub-groups and the question names none, the action is `clarify`, slot `category`, with the published groups as options; groups are never summed or averaged. E5 applies only when no group-level figure exists | RG-4 |
| E2a | When several tables hold the measure and the question names no source, the gold uses the table built for the measure (SRS vital statistics for infant mortality), and the answer states the source | RG-5 (option A) |
| V7 | A ranking of commodities counts each commodity once, at its highest-valued variety, and the answer names the variety; a ranking of varieties is asked as such | RG-6 |

### How to use this section when validating

1. Read the question (and `prior_turns`) only. Walk Section E in order; apply Section D before
   any `clarify`; for a `clarify` item, choose the slot with Section S.
2. Compare with the gold. Record each disagreement in `data/eval/validation/<set>_<validator>.csv`
   with columns `id, field, gold, proposed, rule, note`; `rule` is the id from this section.
3. The author answers each row (agree or dispute). The member who is neither author nor validator
   settles disputes, citing a rule.
4. Agreed changes set `"validated": true`, `"validated_by"` and `"gold_version": 2`, and are listed
   in the judgement table below with the rule. Split membership does not change.

## Validation and judgement items

Milestone 4 (17-19 November 2026): the procedure below was planned; no item was marked
`validated`. Milestone 5 validates every dev and test item against the rules of the previous
section.

Milestone 5 (26 November 2026): all 190 items of `e2e_v1` (100), `e2e_dev_extra` (20),
`e2e_dev_m5` (30) and `e2e_test_ext` (40) were validated against expected-action rules v2 and
the six rules added on 26 November. Each item was checked three ways: the gold, the action the
rules require from the question and the tables alone, and the action the frozen agent (commit
86a36a7) takes by design (`data/eval/validation/alignment_audit.csv` and
`alignment_test_ext.csv`). A gold field changed only where a rule says the gold is wrong; where
the gold follows the rules and the agent does not, the item is an agent error and the gold is
unchanged. Proposed changes were drafted with the rule they cite and decided row by row by Sathya
Prakash (T3), Shaoni Samanta (T1) and Shivanshu Gupta (T2); every change is recorded on its item
(`gold_changes`, `gold_version` 2). Changed items: e2e-075 (tie, V5), e2e-113 (decline to
clarify, E9b), e2e-108 and e2e-095 (tables listed for a search, E2), e2e-070 (each crop once,
V7), e2e-031 (slot named `place`, S2), e2e-227 (follow-up gives the new crop only, F1). The four
items disputed in Milestone 4 were settled by rule: e2e-008 (E10), e2e-013 (E9) and e2e-044
(S1) keep their gold; e2e-031 as above. The hand-filled fields `domain`, `clarify_slot` and
`clarify_options` were drafted from labelling guide 1.1 and decided the same way (e2e-089 set to
`multiple`, M7).


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
