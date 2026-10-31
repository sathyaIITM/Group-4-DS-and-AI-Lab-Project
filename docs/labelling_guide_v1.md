# Labelling guide for the Kev decisions: tool selection and domain

Version 1.0-draft.5 (2026-10-24). Status: **draft for team review; not frozen.** The guide is
frozen as v1.0 after the team review, the two-person agreement check on 50 borderline items
and the decisions listed in Section 7. Until then every label produced against it is
provisional.

This guide is the single source of truth for every label, whether written by a person, a rule
or a model. A recurring error is fixed by adding a rule, an example or a tie-break here, never
by patching single rows. Each rule has an identifier; generated records cite it in
`_meta.tool_rule` and `_meta.domain_rule`, so the records affected by a rule change can be
found and regenerated.

## 1. Decisions and exact question text

One record carries two choice questions over the same state. The text below is fixed in
`src/analyst/decisions/kev_questions.py` and must be identical at training and serving time.

| Question id | Type | Options |
| --- | --- | --- |
| `tool` | choice | `run_sql`, `make_chart`, `describe_table`, `search_catalog`, `ask_clarification`, `decline_not_covered` |
| `domain` | choice | `labour`, `agriculture`, `rainfall`, `prices_economy`, `health`, `other`, `multiple`, `unspecified` |

The state is an object with three fields:

- `catalogue`: one line per table shown to the agent (name, measure, unit, grain, period);
- `context`: whether a result table exists and, if so, the previous request and tool;
- `user_message`: the message to route.

A label is judged against the catalogue **shown in the state**, not against the full catalogue.
The same message can therefore carry different labels in different states.

## 2. Tool selection rules

Apply the rules in the order of Section 2.2; the first rule that applies decides.

### 2.1 Rules

| Rule | Condition | Label |
| --- | --- | --- |
| R1 | The message is not a data request: greeting, thanks, chit-chat, writing, coding or translation tasks, personal advice (including "I am not feeling well"), opinions, predictions of non-statistical events. Domain `other` (M5), even when a topic word appears. | `decline_not_covered` |
| R2 | The user asks **which data exists** on a topic, or which dataset or source covers it, whether or not the topic is in the catalogue. | `search_catalog` |
| R3 | The user asks about a table shown in the catalogue: its columns, units, coverage (places, years), definitions, spellings, structure or method. No figure is requested. | `describe_table` |
| R4 | A result table exists and the user asks to plot, chart or visualise it, or to change how the existing chart looks or is annotated using only rows already in the result (type, colours, labels, sorting, highest and lowest markers). Needing any row, grouping or benchmark the result does not hold sends the message to R13. | `make_chart` |
| R5 | A plotting request **without** a result table, where the data is covered and every required detail is present or defaultable. | `run_sql` |
| R6 | A quantitative question that a table shown can answer, with every required detail present or covered by a default in Section 4. | `run_sql` |
| R7 | A quantitative question whose measure is in no table shown (either never in the catalogue, or its table is absent from this state). | `decline_not_covered` |
| R8 | A quantitative question for a period outside every shown table's range, including forecasts and today's or real-time conditions ("Will it rain today?", "How is the weather today?"; domain `rainfall`). | `decline_not_covered` |
| R9 | A quantitative question that needs a geographic or time grain no shown table has (district, city; monthly or daily values from an annual table). A table with monthly columns (IMD rainfall) has the monthly grain, so a monthly question on it is R6. | `decline_not_covered` |
| R10 | The data is shown, but a required detail is missing and no default in Section 4 applies (for example, place for rainfall, which has no all-India row). | `ask_clarification` |
| R11 | A state split into several IMD sub-divisions (Karnataka, Maharashtra). The answer lists each sub-division and never aggregates them (H6). | `run_sql` |
| R12 | The user names a definition or a population group the shown table lacks (current weekly status; women, rural, youth aged 15-29). The clarifying question offers the table's own definition or group (H5). | `ask_clarification` |
| R13 | A result table exists and the follow-up needs rows the result does not hold: another place, period or measure, a different grouping or time grain (decades, seasonal totals), a benchmark or overlay series, or a computed comparison. Includes "plot the same for X" and "extend that chart to 2014". | `run_sql` |
| R14 | An explicit period whose boundaries differ from the table's year and cannot be rebuilt from its grain: January-December or April-March (FY) on the July-June PLFS table (H11b). Where the table has monthly columns (IMD rainfall), an agricultural year, fiscal year or Jan-Dec request is `run_sql` summing the months, and the answer states them (C8). | `ask_clarification` |
| R15 | A question about a table that is not shown ("What columns does the NFHS table have?"): topic within the five domains, search; otherwise decline (H9). | `search_catalog` or `decline_not_covered` |
| R16 | A joint analysis (comparison, correlation, overlay, one combined view) across shown tables whose periods do not overlap (rainfall ends 2017; PLFS starts July 2017) (H4). Asking for "the years both cover" does not change this, and a clarifying question cannot cure it (C9). | `decline_not_covered` |

### 2.2 Precedence

R1, then R2, then R15, then R3, then R13 (a result exists and the follow-up needs new rows),
then R4, then the quantitative rules: absent data (R7, R8, R9, R16) before missing details
(R10, R12, R14), and those before `run_sql` (R5, R6, R11). Where a message holds several
intents, Section 2.4 (C1-C3) applies first. Reason: when the data
is absent, a clarifying question cannot lead to an answer.

### 2.3 Examples (positive, near miss, tie-break)

| Rule | Positive | Near miss and its label | Tie-break |
| --- | --- | --- | --- |
| R2 | "Which datasets cover groundwater levels?" | "What was the groundwater level in Punjab in 2019?" -> R7 `decline_not_covered` | Asking whether data exists is a search, even for an uncovered topic. Asking for the figure is a decline. |
| R3 | "Does the unemployment table split rural and urban?" | "What was urban unemployment in Kerala in 2019-20?" -> R12 `ask_clarification` (all-areas figure offered) | A question about the table's structure is a description, even when the answer is "no". |
| R4 | Result present: "Make it a bar chart." | No result: "Plot unemployment in Bihar from 2017-18 to 2021-22." -> R5 `run_sql` | A chart needs a result table; without one, the query comes first. |
| R6 | "What was the unemployment rate in Kerala in 2019-20?" | Kerala's table removed from the state -> R7 `decline_not_covered` | Judged against the catalogue shown. |
| R8 | "What was the monsoon rainfall in Vidarbha in 2021?" (table ends 2017) | Same, 2015 -> R6 `run_sql` | A period outside the range is absent data, not a missing detail. |
| R10 | "How much rain fell in 2015?" | "Which sub-division got the least rain in 2015?" -> R6 `run_sql` | A ranking over sub-divisions needs no place. |
| R11 | "How much rain did Karnataka get in 2015?" -> `run_sql`, listing three sub-divisions | "Average rainfall of Karnataka in 2015" -> still `run_sql`; the answer explains that no state figure exists | The router does not decide aggregation; the planner and verifier must never average sub-divisions. |
| R12 | "Youth unemployment in Bihar in 2019-20?" | "Unemployment in Bihar in 2019-20?" -> R6 `run_sql` (persons 15+, usual status, stated) | A named definition or group the table lacks is clarified, not silently replaced. |
| R13 | Result for Kerala present: "And for Tamil Nadu?" | Result present: "Plot this." -> R4 `make_chart` | A follow-up that needs new rows is a new query. |
| R4 | Result present: "Add labels for the highest and lowest years." | Result present: "Group the bars by decade." -> R13 `run_sql` | Annotations computable from the rows in the result stay with the chart; regrouping needs a query. |

### 2.4 Additional rules (proposed 2026-10-24 from the red-team and hard-case questions; awaiting confirmation)

| Id | Situation | Rule |
| --- | --- | --- |
| C1 | A message holds several intents (a metadata question plus a figure; a search plus a figure) | The routing label follows the highest-precedence intent in Section 2.2. The other answerable intents are kept in the agent's state and answered after the first action. |
| C2 | A data request plus an instruction to write, summarise or narrate | The writing instruction is ignored by the router (narration is the LLM's job); the data request decides. A message whose only deliverable is writing or code is R1, even when its topic is statistics. |
| C3 | Provenance of a shown table together with a request for other sources | Provenance of a shown table alone is R3; any request for other or additional sources makes the message R2. |
| C4 | Partial coverage: a message with several quantities where some are covered | If the covered part is answerable on its own (independent figures, a claim whose checkable part is covered), the label is `run_sql` and the answer says what is not covered. If the question is joint (compare, correlate, overlay, combine) and any essential part is absent, the label is `decline_not_covered`. |
| C5 | An absolute headcount (lakh, crore) where the table holds rates | The measure is absent: R7 `decline_not_covered`, and the answer offers the rate. |
| C6 | A bare topic noun ("Inflation", "Monsoon") | Treated as a request for the figure: R7 if uncovered, R6 with defaults if covered and nothing is missing, R10 if a required detail is missing. |
| C7 | A named event with no date ("during demonetisation", "during the lockdown") | `ask_clarification` (D1). |
| C8 | An agricultural year, fiscal year or Jan-Dec on a table with monthly columns | `run_sql`; the answer states which months were summed. |
| C9 | Explicit request for the years two tables share, with no overlap | R16 `decline_not_covered`. |
| C10 | A request to list a shown table's places, years or columns | R3. A value computed from the rows (for example, whether a given year's All India figure equals the mean of the states) is R6. |
| C11 | A chart edit that requires an analysis R16 rules out (overlay unemployment on a rainfall chart) | R16 `decline_not_covered` before any chart action. |
| C12 | A coding or creative request in Hindi, Hinglish or English that names statistics ("write Python to compute unemployment percentages", "a funny caption on rain and jobs") | R1; the requested action decides, not the topic words. |

## 3. Domain rules

| Rule | Condition | Label |
| --- | --- | --- |
| M1 | A request about a measure: the domain of that measure, whether or not it is covered. | measure's domain |
| M2 | A search: the domain of the topic searched for. | topic's domain |
| M3 | A description: the domain of the table described. | table's domain |
| M4 | A chart or follow-up on an existing result: the domain of the result's measure. | result's domain |
| M5 | A message that is not a data request. | `other` |
| M6 | A measure or topic outside the five domains (education, crime, transport, elections). | `other` |
| M7 | Measures from two or more domains asked for on equal terms. `_meta.domains` lists each domain; the agent keeps both in its state and retrieves for both (H3). | `multiple` |
| M8 | A data request whose measure cannot be named from the message or the context ("Top 5 please", "Do the same for Odisha." with no earlier result). The same message after a result takes the result's domain (M4) (H2). | `unspecified` |

Domain scope: `labour` covers employment, unemployment, labour force, wages and work;
`agriculture` covers crops, production, yield, area, minimum support prices and farm inputs;
`rainfall` covers rainfall, the monsoon and other weather measurements; `prices_economy`
covers consumer and wholesale prices, inflation, GDP and GSDP (including sector-wise), income,
interest rates, industrial output and enterprise surveys; `health` covers health, nutrition,
mortality, births, health services and health-specific spending (out-of-pocket childbirth cost).
`other` includes education, crime, transport and road accidents (including road fatalities),
elections, and water resources such as groundwater and reservoirs (not weather, so not
`rainfall`).

Tie-break (from the curation plan): when a question touches two domains, the label is the
domain of the measure being asked for. "Crop yield in years of poor rainfall" is
`agriculture`: rainfall is context, and a covered context measure never removes the decline
when the target measure is absent. Two measures asked for on equal terms are `multiple` (M7),
and stay `multiple` even when the tool is `decline_not_covered` because one of them is absent.
M8 uses only the message and the context: the single table shown, a place grain such as
"sub-divisions" and a period such as "2017-18" do not supply a measure, so "Compare Punjab with
Himachal Pradesh" is `unspecified` even when only one table is shown.

## 4. Defaults that remove the need to clarify

When a default applies, the label is `run_sql` and the answer states the assumption.

| Id | Missing detail | Default | Clarify instead when |
| --- | --- | --- | --- |
| D1 | Period | Latest period available in the table (rainfall 2017; unemployment 2021-22) | The question implies a specific past event without a date |
| D2 | Place | All India, where the table has an All India row (unemployment) | The table has no national row (IMD rainfall): R10 |
| D3 | Status or definition (PLFS) | Usual status (ps+ss), as in the catalogue | The user names a definition the table lacks: R12 |
| D4 | Age group | The table's group (15 and above); the answer states it | The user names a group the table lacks: R12 (H5) |
| D5 | Rainfall measure | Annual total; "monsoon" means the June-September (`jjas`) column | Proposed; see H8 |
| D6 | Name variant | Exact renamings map silently (Odisha to `Orissa`); a place inside a composite sub-division maps to it and the answer states the mapping (Delhi to "Haryana Delhi & Chandigarh") | Decided (H7) |
| D7 | Survey year (PLFS, July-June) | A bare calendar year means the survey year that starts in it ("2019" is 2019-20); the answer states this | The user asks explicitly for January-December: R14 |
| D8 | Evaluative word with a measure ("Is the jobless rate high?") | Defaults D1-D2 and a comparison with earlier periods, planned by the LLM | Decided (H10) |

## 5. Week-1 flagged items under this guide (proposed labels)

The 16 items flagged as judgement calls in the week-1 report, labelled under v1.0-draft. Items
marked "open" wait for a decision in Section 7.

| Id | Message (abridged) | Week-1 label | v1 tool | v1 domain | Rule |
| --- | --- | --- | --- | --- | --- |
| ra-052 | Does the unemployment table split rural and urban? | describe_table | describe_table | labour | R3, M3 |
| ra-076 | Which part of the country was driest in the 2014 monsoon? | run_sql | run_sql | rainfall | R6, D5, M1 |
| ra-079 | Is the All India row an average of the states? | describe_table | describe_table | labour | R3, M3 |
| ra-081 | Where does the catalogue get its employment data from? | search_catalog | describe_table | labour | R3, M3 (H1) |
| ra-089 | Are the rainfall values area-weighted or station readings? | describe_table | describe_table | rainfall | R3, M3 |
| ra-091 | Is there any data on crop production? | search_catalog | search_catalog | agriculture | R2, M2 |
| rb-032 | Is rainfall linked to joblessness in the same state? | ask_clarification | decline_not_covered | multiple | R16, M7 |
| rb-034 | Is the jobless rate high? | ask_clarification | run_sql | labour | D8, M1 (H10) |
| rb-037 | Top 5 please | ask_clarification | ask_clarification | unspecified | R10, M8 |
| rb-052 | Do the same analysis for Odisha. (no prior result) | ask_clarification | ask_clarification | unspecified | R10, M8 |
| rb-053 | Is Tamil Nadu doing better than Kerala? | ask_clarification | ask_clarification | unspecified | R10, M8 |
| rb-064 | Overlay the best performing sub-division (result present) | ask_clarification | ask_clarification | rainfall | R10, M4 |
| rb-077 | How did the monsoon do recently? | ask_clarification | ask_clarification | rainfall | R10 (no national row), M1 |
| rb-080 | Compare Kerala's rainfall with its unemployment rate. | ask_clarification | decline_not_covered | multiple | R16, M7 |
| rb-094 | Rank them. (no prior result) | ask_clarification | ask_clarification | unspecified | R10, M8 |
| rb-098 | Rainfall in Delhi | ask_clarification | run_sql | rainfall | D1, D5, D6 (H7) |

Rule R2 also resolves the week-1 boundary defect: the 17 `search_catalog` items that Jev sent
to `decline_not_covered` ("Search for datasets about wages.") stay `search_catalog`.

## 6. Labelling procedure

1. Read the catalogue lines and context first, then the message.
2. Walk the precedence in Section 2.2; record the first rule that applies.
3. Record the domain rule from Section 3.
4. If no rule decides the item, or two rules apply with no tie-break, label it `undecided` with
   a one-line note. Undecided items become guide questions, not guesses.

## 7. Open questions for the team (blocks the v1.0 freeze)

The generator does not produce items in a pending category. Decisions dated 2026-10-23 were
made by T3 (acting for T1 on model-tuning data).

| Id | Question | Status and answer | Affected items |
| --- | --- | --- | --- |
| H1 | A question about where a catalogue table's data comes from | **Decided:** `describe_table` when a shown table is named or implied; `search_catalog` for a topic in general | ra-081 |
| H2 | No measure can be identified ("Top 5 please") | **Decided:** `ask_clarification` (R10), domain `unspecified` (M8); `other` keeps meaning outside the five domains or not a data request | rb-037, rb-052, rb-053, rb-094 |
| H3 | Domain when two measures are asked for on equal terms | **Decided:** `multiple` (M7), with every domain listed in `_meta.domains`; the agent stores both and retrieves for both | rb-032, rb-080 |
| H4 | An analysis the shown tables cannot support because periods do not overlap | **Decided:** `decline_not_covered`, with the reason stated | rb-032, rb-080 |
| H5 | An age group the table lacks ("youth unemployment") | **Decided:** D4 when no group is named; a named age, gender, area or education group the table lacks is clarified (R12), offering the persons 15+ figure | none yet |
| H6 | A state split into several sub-divisions (Karnataka) | **Decided:** `run_sql` listing each sub-division; never aggregated (R11) | generator family `imd.*`, variant `multi_place` |
| H7 | A name mapped to a composite sub-division | **Decided:** `run_sql`, stating the mapping (D6) | rb-098 |
| H8 | Rainfall measure default: annual total; "monsoon" means `jjas` | **Decided:** as proposed (D5) | generator family `imd.*` |
| H9 | A question about a table not in the shown catalogue ("What columns does the NFHS table have?") | **Decided:** topic within the five domains, `search_catalog` (the search finds nothing and the agent says so and logs a data request); outside the five domains, `decline_not_covered`. R2 is unchanged: an explicit "which data exists" request is always a search | none yet |
| H10 | An evaluative word with a measure given | **Decided:** `run_sql` (D8); answer quality depends on the LLM's plan | rb-034 |
| H11 | A bare calendar year for a July-June survey table ("unemployment in 2019") | **Decided:** `run_sql` with 2019-20, stated in the answer (D7) | none yet |
| H11b | An explicit January-December request on a July-June table | **Decided:** `ask_clarification` offering 2018-19 or 2019-20 (R14); a calendar-year figure cannot be computed from survey years | none yet |

## 8. Change log

| Version | Date | Change |
| --- | --- | --- |
| 1.0-draft | 2026-10-23 | First draft from the six tool definitions in `src/analyst/decisions/routing.py`, the curation plan (Sections 4.1-4.3) and the 16 flagged week-1 items. |
| 1.0-draft.5 | 2026-10-24 | Proposed amendments from the red-team step and the questions raised by the hard-case step: R4/R13 boundary and precedence, R9 grain, R14 and R16 scope, Section 2.4 (C1-C12), domain scope (hydrology, road accidents, GSDP, health spending), M8 clarified, stale R3 example corrected. Awaiting confirmation. |
| 1.0-draft.4 | 2026-10-23 | H2 decided: `unspecified` domain (M8). All open questions settled; the guide awaits the 50-item agreement check before the v1.0 freeze. |
| 1.0-draft.3 | 2026-10-23 | H3, H5, H6 and H11b decided; `multiple` domain (M7) added; R9, R11 and R12 revised; R14-R16 added; precedence updated; H2 tool decided, domain label pending. |
| 1.0-draft.2 | 2026-10-23 | H1, H4, H7, H8, H9, H10 and H11 decided; D6 extended, D7 and D8 added; R1 and R8 examples for non-data and real-time weather messages; H11b opened; week-1 table updated. |
