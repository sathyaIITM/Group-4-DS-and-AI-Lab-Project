# Labelling guide for the Kev decisions: tool selection and domain

Version 1.1-draft (2026-11-25): version 1.0 plus the clarifications K1-K15 of Section 2.5 and
the coverage table of Appendix A; no rule and no question text changed. Version 1.0
(2026-11-17), below, was **frozen for Milestone 4.** The decisions of Section 7 and
the rules of Section 2.4 are confirmed. The planned two-person agreement check on 50 borderline
items was not run separately: the `dev_human` set takes its place, since each of its 200 items
is labelled by hand by two members against this version and Cohen's kappa is reported per
decision. A rule found unclear there is clarified in version 1.1, and the affected stratum is
labelled again.

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
| `tool` | choice | `run_sql`, `make_chart`, `describe_table`, `search_catalog`, `ask_clarification`, `decline_not_covered`, `explain_result` |
| `domain` | choice | `labour`, `agriculture`, `rainfall`, `prices_economy`, `health`, `other`, `multiple`, `unspecified` |

The state is an object with three fields:

- `catalogue`: one line per table shown to the agent (name, measure, unit, grain, period); in
  the agent these are the top-4 catalogue candidates retrieved for the message, built the same
  way for training and serving;
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
| R15 | A question about a table that is not shown ("What columns does the NFHS table have?"): topic within the five domains, search; topic outside the five domains, decline (H9). "Not shown" refers to the top-4 candidates in the state. This rule never declines a data request whose topic is covered by a shown table: a shown NCRB table is handled by the ordinary rules even though its domain is `other`. | `search_catalog` or `decline_not_covered` |
| R16 | A joint analysis (comparison, correlation, overlay, one combined view) across shown tables whose periods do not overlap (rainfall ends 2017; PLFS starts July 2017) (H4). Asking for "the years both cover" does not change this, and a clarifying question cannot cure it (C9). | `decline_not_covered` |
| R17 | A result table exists and the user asks about that result itself: where its figures come from (source, table, query), how they were computed, or which definition, period, assumption, default or caveat applies. No new figure, place, period or measure is requested; a follow-up that needs new rows is R13. Without a result there is nothing to explain: a message that names no table or topic is `search_catalog` (domain `unspecified`, M8), and one that names a shown table is R3 (H1). | `explain_result` |

### 2.2 Precedence

R1, then R2, then R15, then R17 (a result exists and the message asks only about it), then R3, then R13 (a result exists and the follow-up needs new rows),
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
| R17 | Result present: "Where does this number come from?" | No result: same message -> R2 `search_catalog`, domain `unspecified`. Result present: "And what was it in 2020-21?" -> R13 `run_sql` | Questions about the stored result are answered from its evidence; anything that needs new rows is a query. |
| R4 | Result present: "Add labels for the highest and lowest years." | Result present: "Group the bars by decade." -> R13 `run_sql` | Annotations computable from the rows in the result stay with the chart; regrouping needs a query. |

### 2.4 Additional rules (proposed 2026-10-24 from the red-team and hard-case questions; confirmed 2026-11-17)

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

### 2.5 Clarifications in version 1.1 (draft, 2026-11-25)

The 198 labelled items of `dev_human` v1 agree on the tool at Cohen's kappa 0.70, below the target
of 0.80. The 50 tool disagreements fall into the groups below. Each clarification restates how
the rules of Sections 2.1-2.4 and 4 already decide the case, adds a positive example, a near miss
and a tie-break, and changes no rule. The final labels of the adjudicated disagreements are the
examples. The routing training data (generated under rules R1-R17) needs no regeneration; a
conflict found later is recorded in Section 8 and left for the next data version.

| Id | Disagreement (items) | Clarification | Positive | Near miss and its label | Tie-break |
| --- | --- | --- | --- | --- | --- |
| K1 | `run_sql` vs `decline_not_covered` (17) | Coverage is read from the catalogue lines shown, never from memory: the measure must be one of the table's indicators (R7), the period inside its range (R8) and the place at a level it holds (R9). Appendix A lists the range and levels of every published table | "Unemployment rate in Kerala in 2023-24" -> R8 `decline_not_covered` (the table ends 2021-22) | "Maharashtra per capita GSDP 2020-21" -> R6 `run_sql` (inside 2019-20 to 2023-24) | Check measure, then period, then level, against Appendix A; the first that fails decides (R7, R8, R9) |
| K2 | "latest", "current", "now" against R8 (part of K1) | A request for the latest or current value of a published statistic is D1 (latest period the table holds), stated in the answer. R8 covers forecasts and real-time conditions only | "CPI general index, urban, for the latest month" -> R6 `run_sql` with D1 | "Will it rain today?" -> R8 `decline_not_covered` | A published statistic: D1. Weather, events or prices of today or later: R8 |
| K3 | Two figures in one message (part of K1) | Independent figures from different tables are answered (C4); a joint analysis (compare, overlay, correlate) across tables whose periods do not overlap is declined (R16) | "Wheat MSP for 2022-23 and the CPI cereals index for March 2023" -> R6 `run_sql` | "Compare the wheat MSP with mandi wheat prices in 2020" -> R16 `decline_not_covered` (the Mandi table is one day in 2026) | Is a single combined answer requested? Yes: check R16. No: C4 |
| K4 | `ask_clarification` vs `decline_not_covered` (7) | A message that asks for a figure, a comparison or a ranking but names no measure is a data request: R10 `ask_clarification`, domain `unspecified` (M8). R1 applies only when no figure is requested at all | "numbers for Bihar pls", "Which state is the best?" -> R10 | "Thanks, that helps" -> R1 `decline_not_covered` | Does the message ask for any number, comparison or ranking? Yes: never R1 |
| K5 | `ask_clarification` vs `run_sql` (9) | Before R10, check in order: a named group or definition the table lacks (R12), an explicit year boundary the table cannot rebuild (R14), an undated event (C7). Then apply the defaults of Section 4; R10 only if a required detail is still missing. D2 (All India) applies only to tables with a national row (Appendix A); IMD sub-division, Mandi and district tables have none | "unemployment rate in 2019" -> R6 `run_sql` (D2, D7) | "Rainfall figures for the 1999 monsoon?" -> R10 (no place; no national row); "Female unemployment in UP in 2018-19" -> R12 | Named group or definition absent: R12. Explicit FY or Jan-Dec on PLFS: R14. Event without date: C7. Else a default, else R10 |
| K6 | `search_catalog` vs `decline_not_covered` (4) | The form of the message decides: asking whether data exists, or asking about a table (its years, columns, source), is never R7. Within the five domains or a shown table: R2, R15 or R3; a table outside the five domains that is not shown: R15 decline | "Kya aapke paas literacy ka data hai?" -> R2 `search_catalog` | "Literacy rate of Bihar in 2011?" -> R7 `decline_not_covered` | A question about data or tables: R2, R3 or R15. A request for the figure: R7 |
| K7 | `ask_clarification` vs `search_catalog`, no result present (4) | With no earlier result, a question about "this" or "that" figure's source or method is R17's fallback: `search_catalog`, domain `unspecified`. A request for a new figure that refers to "that" ("Can you repeat that for Jharkhand?") is a data request with no measure: R10 | "what's the source for that figure?" (no result) -> `search_catalog` | "And the national figure?" (no result) -> R10 `ask_clarification` | No result and the message asks about provenance or method: search. Asks for a figure: R10 |
| K8 | Chart requests with a result present (4) | An annotation computable from the rows of the result is R4. A new series or measure is R13; if the periods do not overlap, R16 (C11). A criterion the user has not defined ("best", "important") is R10 | "chart these two together" (both series in the result) -> R4 `make_chart` | "Overlay unemployment on this chart" (rainfall result) -> R16; "Highlight the best one" -> R10 | Rows already in the result and a defined criterion: R4 |
| K9 | A place name that is not a level of the table (1) | A city on a district table: the district(s) that carry its name. One district: R6 with the mapping stated (D6). Several ("Bangalore": Bangalore Urban, Bangalore Rural): R10, offering them | "Normal rainfall for Bangalore?" -> R10 | "Normal rainfall for Pune district?" -> R6 | Count the matching districts in the table: one R6, several R10, none R9 |
| K10 | Metadata plus a figure, provenance with a shown table (3) | C1 applies: the highest-precedence intent decides (R3 before R6). A question whether a shown table covers a place or year is R3. With a result present, a question about the sources of its numbers is R17 | "What's the unit in the IMR table, and what was Punjab's IMR in 2016?" -> R3 `describe_table` | "Which sources are these two numbers from?" (result present) -> R17 `explain_result` | Result present and the question is about the result: R17. Else a named shown table: R3 |
| K11 | Follow-up "the same for X" with a result (1) | A follow-up that needs another place, period or measure is R13 `run_sql`, even when the earlier result was a chart | "Now do the same for Tamil Nadu" -> R13 `run_sql` | "Make it a bar chart" -> R4 | New rows needed: R13 |

Proposals carried from the Milestone 4 data review (D3, 2026-11-17), stated here as clarifications:

| Id | Case | Label |
| --- | --- | --- |
| K12 | A district rainfall figure for a given year (the district table holds 1951-2000 normals only) | R9 `decline_not_covered`; a question about the normal rainfall of a district is R6 |
| K13 | A bare "Inflation" with `cpi_all_india` shown | R6 `run_sql` with defaults: latest month, combined (Rural+Urban) general index, year-on-year change computed from the index, stated. A request for an index value alone is R6 on the index |
| K14 | Labour force participation with no area or status named (the table holds urban areas, current weekly status) | R6 `run_sql`; the answer states the table's population and status (as D3, D4). A named group the table lacks (rural, youth) is R12 |
| K15 | Out-of-pocket spending | Childbirth in a public facility (NFHS indicator) is covered: R6, domain `health`. Hospitalisation or general health spending is not: R7, domain `health` |

## 3. Domain rules

| Rule | Condition | Label |
| --- | --- | --- |
| M1 | A request about a measure: the domain of that measure, whether or not it is covered. | measure's domain |
| M2 | A search: the domain of the topic searched for. | topic's domain |
| M3 | A description: the domain of the table described. | table's domain |
| M4 | A chart, explanation (R17) or follow-up on an existing result: the domain of the result's measure. | result's domain |
| M5 | A message that is not a data request. | `other` |
| M6 | A measure or topic outside the five domains (education, crime, transport, elections). | `other` |
| M7 | Measures from two or more domains asked for on equal terms. `_meta.domains` lists each domain; the agent keeps both in its state and retrieves for both (H3). | `multiple` |
| M8 | A data request whose measure cannot be named from the message or the context ("Top 5 please", "Do the same for Odisha." with no earlier result). The same message after a result takes the result's domain (M4) (H2). | `unspecified` |

Domain scope: `labour` covers employment, unemployment, labour force, wages and work;
`agriculture` covers crops, crop production, yield, area, minimum support prices (MSP) and farm
inputs;
`rainfall` covers rainfall, the monsoon and other weather measurements; `prices_economy`
covers consumer and wholesale prices, market and retail commodity prices (including Mandi
arrival prices, even for farm produce), inflation, GDP and GSDP (including sector-wise), income,
interest rates, industrial output and enterprise surveys; `health` covers health, nutrition,
mortality, births, health services and health-specific spending (out-of-pocket childbirth cost).
`other` includes education, crime, transport and road accidents (including road fatalities),
elections, and water resources such as groundwater and reservoirs (not weather, so not
`rainfall`).

Two boundary rules (agent_graph.md v0.3, decision 12, 2026-11-05):

- **Prices of farm produce.** A market, wholesale or retail price of a commodity (Mandi modal,
  minimum or maximum price; onion retail price) is `prices_economy`. A minimum support price
  (MSP) and crop production, area or yield are `agriculture`. "Onion price in Lasalgaon mandi"
  is `prices_economy`; "MSP of paddy in 2023-24" is `agriculture`; "Compare the MSP of wheat
  with its mandi price" is `multiple` (M7).
- **`other` is a domain, not a decline.** `other` with a covered table (the NCRB crime tables)
  follows the ordinary tool rules: "How many murders were recorded in Bihar in 2022?" with the
  NCRB table shown is R6 `run_sql`, domain `other`.

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
2. Walk the precedence in Section 2.2; record the first rule that applies. For R7, R8 and R9,
   check the measure, the period and the place level against Appendix A, not from memory (K1).
   Before R10, check R12, R14, C7 and the defaults of Section 4 (K5).
3. Record the domain rule from Section 3.
4. If no rule decides the item, or two rules apply with no tie-break, label it `undecided` with
   a one-line note. Undecided items become guide questions, not guesses.

## 7. Decisions on the open questions (all decided; recorded for the v1.0 freeze)

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
| H9 | A question about a table not in the shown catalogue ("What columns does the NFHS table have?") | **Decided:** topic within the five domains, `search_catalog` (the search finds nothing and the agent says so and logs a data request); outside the five domains *and* not shown, `decline_not_covered` (amended 2026-11-05: a shown `other` table follows the ordinary rules). R2 is unchanged: an explicit "which data exists" request is always a search | none yet |
| H10 | An evaluative word with a measure given | **Decided:** `run_sql` (D8); answer quality depends on the LLM's plan | rb-034 |
| H11 | A bare calendar year for a July-June survey table ("unemployment in 2019") | **Decided:** `run_sql` with 2019-20, stated in the answer (D7) | none yet |
| H11b | An explicit January-December request on a July-June table | **Decided:** `ask_clarification` offering 2018-19 or 2019-20 (R14); a calendar-year figure cannot be computed from survey years | none yet |

## 8. Change log

| Version | Date | Change |
| --- | --- | --- |
| 1.1-draft | 2026-11-25 | Section 2.5: clarifications K1-K11 from the 50 tool disagreements of `dev_human` v1 (kappa 0.70), each with the adjudicated label as its example, and K12-K15 from the four Milestone 4 proposals; Section 6 coverage and pre-R10 checks; Appendix A coverage table of the 14 published tables. No rule or question text changed, so `GUIDE_VERSION` in `kev_questions.py` and the routing data are unchanged. Used to re-adjudicate the 50 tool disagreements (`dev_human` v1.1) |
| 1.0-draft | 2026-10-23 | First draft from the six tool definitions in `src/analyst/decisions/routing.py`, the curation plan (Sections 4.1-4.3) and the 16 flagged week-1 items. |
| 1.0 | 2026-11-17 | Frozen for Milestone 4: Section 2.4 (C1-C12) confirmed; Section 7 complete. The separate 50-item agreement check is replaced by the two-labeller `dev_human` set and its kappa per decision. `GUIDE_VERSION` set to `1.0`. |
| 1.0-draft.6 | 2026-11-12 | Decisions of 2026-11-05 applied: seventh tool option `explain_result` (R17, precedence after R15, example row, M4 extended); Mandi and other market prices are `prices_economy`, MSP and crop production are `agriculture`; `other` with a shown table follows the ordinary rules (R15, H9); the state's catalogue is the top-4 candidates. `GUIDE_VERSION` in `kev_questions.py` set to `1.0-draft.6`. Domain option text unchanged, so the v1 domain splits remain valid. |
| 1.0-draft.5 | 2026-10-24 | Proposed amendments from the red-team step and the questions raised by the hard-case step: R4/R13 boundary and precedence, R9 grain, R14 and R16 scope, Section 2.4 (C1-C12), domain scope (hydrology, road accidents, GSDP, health spending), M8 clarified, stale R3 example corrected. Awaiting confirmation. |
| 1.0-draft.4 | 2026-10-23 | H2 decided: `unspecified` domain (M8). All open questions settled; the guide awaits the 50-item agreement check before the v1.0 freeze. |
| 1.0-draft.3 | 2026-10-23 | H3, H5, H6 and H11b decided; `multiple` domain (M7) added; R9, R11 and R12 revised; R14-R16 added; precedence updated; H2 tool decided, domain label pending. |
| 1.0-draft.2 | 2026-10-23 | H1, H4, H7, H8, H9, H10 and H11 decided; D6 extended, D7 and D8 added; R1 and R8 examples for non-data and real-time weather messages; H11b opened; week-1 table updated. |

## Appendix A. Coverage of the published tables (catalogue of 2026-11-17)

From `data/processed/catalogue.json`. "National row" means the table holds an All India row
besides its States (D2); a table that is itself national (CPI, MSP, NCRB annual) answers All
India questions directly.

| Table | Measure | Domain | Levels | National row | Coverage | Period type |
| --- | --- | --- | --- | --- | --- | --- |
| `cpi_all_india` | Consumer Price Index (base 2012 = 100), rural, urban and combined | prices_economy | national | table is national | Jan 2013 to Dec 2023 (April 2019 missing) | month |
| `crop_production_district` | Crop area and production by district, season and crop year | agriculture | district | no | 1997-98 to 2015-16 | crop year |
| `gsdp_per_capita_state` | Per capita GSDP (rupees), current prices, 28 States | prices_economy | state | no | 2019-20 to 2023-24 | fiscal year |
| `imd_district_rainfall_normals` | Normal rainfall (mm) by district, average of 1951-2000 | rainfall | district | no | normals only (no yearly values) | 1951-2000 average |
| `imd_subdivision_monthly_rainfall` | Rainfall (mm) by month, season and year, 36 sub-divisions | rainfall | sub-division | no | 1901 to 2017 | calendar year, month, season |
| `mandi_daily_prices` | Mandi minimum, maximum and modal prices (INR per quintal) | prices_economy | market | no | one day: 29 Oct 2026 | date |
| `msp_crops` | Minimum support prices (INR per quintal), 24 crops | agriculture | national | table is national | 2013-14 to 2024-25 | crop year |
| `ncrb_annual_crime_statistics` | National crime incidence and rates | other | national | table is national | 2022 to 2024 | calendar year |
| `ncrb_violent_crimes_state` | Violent crimes (incidence) by State/UT | other | national, state | yes | 2021 to 2023 | calendar year |
| `nfhs5_district_indicators` | NFHS-5 district indicators | health | district | no | 2019-21 (one round) | survey round |
| `nfhs5_state_factsheet` | NFHS-5 State/UT indicators, total, urban and rural | health | national, state | yes | 2019-21 (one round) | survey round |
| `plfs_lfpr_urban_state` | Labour force participation rate (%), current weekly status, urban areas | labour | national, state | yes | 2023-24 (July-June) | survey round |
| `plfs_state_ur_usual_status` | Unemployment rate (%), usual status (ps+ss), persons 15+ | labour | national, state | yes | 2017-18 to 2021-22 (July-June) | survey year |
| `srs_imr_state` | Infant mortality rate (per 1,000 live births), SRS | health | national, state | yes | 2015 to 2019 | calendar year |
