# Milestone 4: Model Training, Configuration and Evaluation

Project: Analyst Agent for Indian Public Data with Calibrated Decision Models (working title).
Course: DS & AI Lab, GenAI track, Group 4. Date: 19 November 2026. Version 0.8.

**Status of this file.** Complete for submission; each member's sign-off is recorded in the
Sign-off section. Every
result cites the committed file that holds it and the command that produced it (Appendix A and
Section A6.7).

**Scope of the evidence.** As in Milestone 3, every statement is tagged:

| Tag | Meaning |
| --- | --- |
| **Built** | Code exists in the repository and is covered by tests |
| **Measured** | A run was performed and its output is committed, with the command that produced it |
| **Designed** | Specified in [`docs/specs/agent_graph.md`](../../docs/specs/agent_graph.md) and not yet implemented |
| **Estimate** | A planning figure, not a measurement |
| **Self-reported** | A figure published by a vendor or project, not reproduced by the team |

## Document change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | 12 Nov 2026 | Skeleton: structure, requirement map, training configuration facts |
| 0.2 | 17 Nov 2026 | Hosted LLM layer configuration and the Vertex AI access and thinking check (Section A2) |
| 0.3 | 19 Nov 2026 | Part B under the twelve guideline headings (training, selection, test results, gate, cascade); Section 2.3 (`dev_human`) |
| 0.4 | 19 Nov 2026 | Section A6: version ladder v0 to v2 on the development and test sets, error analysis, sample outputs |
| 0.5 | 19 Nov 2026 | Response to the Milestone 3 review (1.2), status (1.3), key findings (4), artifacts and reproduction (Appendix A) |
| 0.6 | 19 Nov 2026 | Sections A4 and A5 brought in line with A6; evaluation-set wording; scoring rules (A6.1) |
| 0.7 | 19 Nov 2026 | Two-tier comparison (E2) closed; Laya plan; calibration wording in B8 and Section 4 corrected; slides |
| 0.8 | 19 Nov 2026 | Sections 2.1, 2.2, A1 and A2 written; hosted LLM configuration (A2.x) brought up to the evaluated configuration; A3 and A4 updated; contribution log and sign-off |

## 1. Introduction

### 1.1 Requirement map

The report gives equal weight to the agent system (Part A) and the decision models (Part B).
The TA confirmed that fine-tuning and calibrating the decision models is part of Milestone 4
training. For the agent, training is read as configuring and tuning the system on the
development set, and measuring it end to end.

| Course requirement | Part A: agent system | Part B: decision models |
| --- | --- | --- |
| Training configuration | Section A2; [`configs/agent.yaml`](../../configs/agent.yaml), [`configs/model.yaml`](../../configs/model.yaml), [`configs/inference.yaml`](../../configs/inference.yaml), [`configs/prompts/`](../../configs/prompts/) | Sections B2-B5; [`configs/train.yaml`](../../configs/train.yaml) |
| Hyperparameter experiments | Section A4 | Sections B6-B8 |
| Generalisation and stability | Section A5 | Sections B6, B8 and B12 (seeds, horizon, option order) |
| Results and sample outputs | Section A6 | Sections B9, B10 and B12 |
| Training artifacts | Appendix A | Appendix A; [`models/registry.json`](../../models/registry.json) |
| Key findings | Section 4 | Section 4 |

### 1.2 Response to the Milestone 3 review

The Milestone 3 report moved eight items to Milestone 4. Their state on 19 November:

| Item promised in Milestone 3 | State | Where |
| --- | --- | --- |
| 1. Human-labelled routing set (two labellers, agreement, results per label) | **Done.** 200 items, two labellers per item and an adjudicator; 198 kept; Cohen's kappa domain 0.88, tool 0.70; per-label F1 reported | Sections 2.3 and B12 |
| 2. About 100 evaluation questions with outcomes fixed in advance by a member who did not write the pipeline, at least 20 to decline or clarify | **Done.** `e2e_v1`: 100 questions written by T1, 12 to decline and 8 to clarify. Validation and extension of the set are required to enhance the agent and to test it extensively | Section 2.2; [`data/eval/e2e_v1.jsonl`](../../data/eval/e2e_v1.jsonl) |
| 3. v0 and the retrieval configurations on that set, three runs each | **Done.** v0, v1 and v2, 3 runs x 60 test questions each | Sections A4-A6; [`version_ladder_test.md`](../../outputs/reports/version_ladder_test.md) |
| 4. Fair Kev and Laya comparison (same split, same calibration, human labels) | **Done for Kev; Laya in the following week.** Kev zero-shot, Kev fine-tuned and Jev on the same human labels with the same calibration procedure. Kev was taken forward because its zero-shot accuracy on `dev_synthetic` was well above Laya's (0.823 against 0.473); a fine-tuned Laya run is planned for the following week and will be reported then | Sections B11 and B12 |
| 5. Full graph merged, with result checks tied to the intent | **Built.** Graph, control, model and tool nodes merged; intent-tied result checks and the narrated-number check run in the live graph | Section A3; [`src/analyst/agents/`](../../src/analyst/agents/) |
| 6. Catalogue freeze, reviewed guidance cards, new verified examples, retrieval recall at 4 | **Done.** 14 tables frozen; guidance cards version 3 and verified examples version 2; catalogue retrieval recall at 4 of 1.0 in every query category of the audit, and recall 1.0 with MRR 0.86 on the 40 `e2e_dev` cases | [`catalogue_retrieval_audit.json`](../../outputs/reports/catalogue_retrieval_audit.json), [`retrieval_agent_e2e_dev.v1.json`](../../outputs/reports/retrieval_agent_e2e_dev.v1.json) |
| 7. Vertex AI and the two-tier Gemini comparison | **Vertex AI done; comparison closed.** All runs use `gemini-3.5-flash-lite`. The team closed the two-tier comparison (E2) on 19 November as not required: the default tier is kept | Section A2; [`configs/model.yaml`](../../configs/model.yaml) |
| 8. Configuration files `model.yaml`, `train.yaml`, `inference.yaml`, `evaluation.yaml` | **Done**, with `agent.yaml` | [`configs/`](../../configs/) |

### 1.3 Status

| Area | State | Evidence |
| --- | --- | --- |
| Agent graph with hosted LLM, retrieval and deterministic tools | **Built**; runs end to end on the frozen catalogue | Part A |
| Version ladder v0, v1, v2 on `e2e_test` (3 x 60) | **Measured**: success 0.683, 0.689, 0.694; execution accuracy 0.433, 0.525, 0.633; cost per answer USD 0.0269, 0.0296, 0.0190 (estimates) | [`version_ladder_test.md`](../../outputs/reports/version_ladder_test.md) |
| Kev-0.8B domain decision | **Measured**: 8 runs trained, `ep3` selected on validation, 0.980 accuracy on `dev_human`; gate passed | Part B |
| Kev inside the agent (v4) | Not yet: routing in the ladder is done by the hosted LLM (v0, v1) or by Jev (v2); Kev takes over the domain decision in v4 | Sections A6.1 and 4 |
| Calibrated verification by Jev (v5), prompt optimisation (v3) | Not started; next milestone | - |
| Drift baseline and log collation | **Built**; no real baseline yet | Section 3 |

## 2. Data and evaluation sets

### 2.1 Catalogue after the freeze

**Built (T1).** The catalogue is frozen at 14 tables from government sources (data.gov.in API
copies, the canonical raw files from 17 November), built by the configuration-driven pipeline of
Milestone 2 into one observation table per dataset (`obs_<dataset>`) and described in
`data/processed/catalogue.json` (hashes in
[`data/MANIFEST.md`](../../data/MANIFEST.md); the Parquet tables are not in git).

| Dataset | Domain | Geography | Coverage | Observations | Indicators |
| --- | --- | --- | --- | --- | --- |
| `plfs_state_ur_usual_status` | labour | India, State | 2017-18 to 2021-22 (July-June) | 190 | 1 |
| `plfs_lfpr_urban_state` | labour | India, State | 2023-24 (July-June) | 37 | 1 |
| `crop_production_district` | agriculture | District | 1997-98 to 2015-16 (crop years) | 492,182 | 5 |
| `msp_crops` | agriculture | India | 2013-14 to 2024-25 | 348 | 1 |
| `imd_subdivision_monthly_rainfall` | rainfall | 36 sub-divisions | 1901 to 2017 (month, season, year) | 71,196 | 1 |
| `imd_district_rainfall_normals` | rainfall | District | 1951-2000 average | 10,897 | 17 |
| `cpi_all_india` | prices_economy | India | January 2013 to December 2023 (months) | 10,611 | 27 |
| `gsdp_per_capita_state` | prices_economy | State | 2019-20 to 2023-24 (April-March) | 140 | 1 |
| `mandi_daily_prices` | prices_economy | Market | 29 October 2026 (one day) | 49,179 | 3 |
| `nfhs5_state_factsheet` | health | India, State | 2019-2021 survey round | 14,541 | 131 |
| `nfhs5_district_indicators` | health | District | 2019-2021 survey round | 73,528 | 104 |
| `srs_imr_state` | health | India, State | 2015 to 2019 | 185 | 1 |
| `ncrb_annual_crime_statistics` | other | India | 2022 to 2024 | 24 | 8 |
| `ncrb_violent_crimes_state` | other | India, State | 2021 to 2023 | 111 | 1 |

Checks ([`docs/specs/catalogue_check.md`](../../docs/specs/catalogue_check.md), `python
scripts/check_catalogue.py --samples 5 --seed 0`): titles, caveats, domains, period conventions,
units, total rows and coverage reviewed against the publisher; 70 of 70 sampled values traced to
their raw cell; `python scripts/run_pipeline.py --verify` passes. Quality flags are kept, not
dropped (for example 357 low-sample and 414 suppressed NFHS-5 State values; 13 implausible mandi
prices; April 2019 absent from all 81 CPI series in the source). Deferred after Milestone 4: State
CPI, and Census 2011, whose resource page could not be located.

### 2.2 End-to-end evaluation set `e2e_v1`

**Built (T1).** [`data/eval/e2e_v1.jsonl`](../../data/eval/e2e_v1.jsonl): 100 questions whose
outcome is fixed in advance, written from the published tables and the labelling guide (version
1.0) without looking at agent output, by a member who did not write the agent
([`data/eval/README.md`](../../data/eval/README.md)).

| Dimension | Count |
| --- | --- |
| Expected action | answer 71, decline 14, clarify 8, describe 4, search 3 |
| Questions per published table | 5 to 8 (all 14 tables) |
| Derived values (percentage change, percentage points, share) | 13 |
| Items testing a named convention (survey year, fiscal year, sub-division, suppressed value, and others) | 52 |
| Follow-ups with earlier turns | 11 |
| Split | `e2e_dev` 40 and `e2e_test` 60, stratified by action and table ([`configs/evaluation.yaml`](../../configs/evaluation.yaml)) |

Every gold query is read-only SQL on the observation tables; expected values are taken from its
execution, never typed. `python scripts/check_e2e_set.py` checks shape, action rules, quotas and
every gold query against the tables: 100 items, 0 errors
([`e2e_v1_check.json`](../../outputs/reports/e2e_v1_check.json)). No item overlaps the `dev_human`
items, the samples or the verified examples (character 5-gram Jaccard 0.8). A supplement of 20
development items (`e2e_dev_extra.v1.jsonl`) adds describe, search and clarify cases to the
development set only. The set was validated end to end; a further round of validation, and an
extension of the set, are needed to enhance the agent and to test it extensively. Thirteen items rest
on a recorded judgement (README, section "Validation").

### 2.3 Human-labelled routing set `dev_human`

**Measured.** 200 routing items prepared by T3 to quotas per tool and domain
([`data/labels/dev_human_v1/README.md`](../../data/labels/dev_human_v1/README.md)). Each item was
labelled independently and by hand by two of T1, T2 and T4 under the labelling guide
([`docs/specs/labelling_guide_v1.md`](../../docs/specs/labelling_guide_v1.md), version 1.0); the
third member adjudicated. No model or assistant chose or suggested a label. T3's intended labels
were sealed before labelling (SHA-256 posted to the team) and are compared only after the freeze.

| Quantity | Value |
| --- | --- |
| Near-duplicates against the training data (character 5-gram Jaccard at least 0.8) | None ([`overlap_check.json`](../../data/labels/dev_human_v1/overlap_check.json)) |
| Agreement, Cohen's kappa ([`agreement.json`](../../data/labels/dev_human_v1/agreement.json)) | Domain 0.88 (blocks 0.86, 0.84, 0.95); tool 0.70 (0.68, 0.68, 0.73), below the 0.80 target |
| Adjudicated rows | 72 (27, 28, 17) |
| Removed as ambiguous | 2 of 200 (dh-086, dh-195) |
| Frozen set | 198 items, [`data/splits/kev/dev_human.v1.jsonl`](../../data/splits/kev/dev_human.v1.jsonl), SHA-256 `a2094350…` ([`freeze.json`](../../data/labels/dev_human_v1/freeze.json)) |

Deviation: block A was adjudicated by T3 instead of T4, so that the freeze could be met while T4
labelled blocks B and C; T3 states that the items and the sealed labels were not read beforehand.
The deviation is recorded in the `dev_human` README and on every adjudicated row. Commands:
`python scripts/label_agreement.py agree`, then `freeze --items
data/labels/dev_human_v1/items_rendered.jsonl`. Code:
[`src/analyst/evaluation/dev_human.py`](../../src/analyst/evaluation/dev_human.py),
[`scripts/label_agreement.py`](../../scripts/label_agreement.py),
[`scripts/check_dev_human_overlap.py`](../../scripts/check_dev_human_overlap.py).

## Part A. The agent system

### A1. Build process

**Built (T2, with T3 and T4).** The agent was built contract first. The design contract
([`docs/specs/agent_graph.md`](../../docs/specs/agent_graph.md), version 0.3) fixed the graph, the
state and the data contracts before code was written; the contracts package
[`src/analyst/contracts/`](../../src/analyst/contracts/) implements them as Pydantic models,
field for field, and [`tests/test_contracts.py`](../../tests/test_contracts.py) fails when a
contract drifts from the document. Each track then implemented its nodes against the contracts:
control nodes, graph, memory and run log (T2,
[`control_nodes.py`](../../src/analyst/agents/control_nodes.py),
[`graph.py`](../../src/analyst/agents/graph.py)); model-backed nodes (T3,
[`model_nodes.py`](../../src/analyst/agents/model_nodes.py)); deterministic tool nodes (T4,
[`tool_nodes.py`](../../src/analyst/agents/tool_nodes.py)). Scripted stand-ins
([`stubs.py`](../../src/analyst/agents/stubs.py)) let every path of the graph run and be tested
before the real nodes existed, without a model call.

Integration followed one branch, `docs/milestone-4`: feature branches per track were reviewed and
merged into it, and the full suite (569 tests in 47 files; no failures, 19 skipped), Ruff lint and format and `mypy` were
run at integration. A live smoke run
(`python scripts/run_agent.py --question "Show monthly rainfall in Kerala" --version v0 --llm
live`) and a demonstration application (FastAPI with a browser interface, [`app/api/main.py`](../../app/api/main.py))
were used to test conversations by hand, including follow-ups, clarification replies and changes
of topic; faults found this way were fixed by general rules and recorded in
[`CHANGELOG.md`](../../CHANGELOG.md).

### A2. Architecture and configuration

**Built.** The graph ([`graph.py`](../../src/analyst/agents/graph.py), LangGraph) has 36 nodes
and fixed paths; routers only choose the next node, and every conditional edge applies the run
deadline, the model-call budget and node errors, so a run always ends in one of the terminal
nodes (answer, clarification, decline, abstention, out of scope, system failure).

| Stage | Nodes | What happens |
| --- | --- | --- |
| Intake | `receive_request`, `screen_request` | Reads the conversation memory (last five turns, pending clarification, prior plan and result); a reply to a clarification ("the second one", "all") is read by code; prompt-override attempts are screened out |
| Retrieval | `retrieve_catalogue_candidates`, `retrieve_context_and_examples` | Hybrid retrieval (BM25 fused with `bge-small-en-v1.5`) over one entry per table, top four tables; then indicators, codelists, guidance cards (v1 and later) and verified examples (v2 and later) for those tables |
| Routing | `route_tool_and_domain`, `escalate_to_jev`, `resolve_routing_decision` | Tool and domain decided by the hosted model (v0, v1) or Jev with the model as fallback (v2); seven branches: query, chart, describe, search, explain, clarify, decline |
| Query path | `extract_query_intent` to `verify_numbers_deterministically` | Intent, place and period resolution, coverage, SQL generation and repair, read-only execution, derivations, result checks, narration and the number check |
| Output | `build_evidence_bundle`, `assemble_answer_and_evidence_panel`, `select_chart_type`, `render_chart`, `finalize_response` | Evidence bundle stored for every answer; chart chosen by rules (Vega-Lite); run log written once per run |

Run limits ([`configs/agent.yaml`](../../configs/agent.yaml)): 45 s per run; at most 8 model
calls, 3 SQL generations, 2 SQL repairs, 2 narrations, 2 clarifications and 1 widened catalogue
search; four catalogue candidates. Memory and run log are SQLite files
([`memory.py`](../../src/analyst/agents/memory.py), [`runlog.py`](../../src/analyst/agents/runlog.py);
schema in [`docs/specs/run_log_v1.md`](../../docs/specs/run_log_v1.md)); runs are exported as
bundles for collation (Section 3).

#### A2.x Hosted LLM layer (T3)

**Built.** Client: [`src/analyst/inference/llm.py`](../../src/analyst/inference/llm.py)
(`LlmClient.structured`). Prompt registry:
[`src/analyst/inference/prompts.py`](../../src/analyst/inference/prompts.py); prompts
[`configs/prompts/`](../../configs/prompts/), latest version used: `intent` v9, `sql` v3,
`sql_repair` v1, `narrate` v2, `clarify` v2, `route` v2, `decline` v1, `describe` v1.
Configuration: [`configs/model.yaml`](../../configs/model.yaml). The table gives the configuration
of the evaluated commit `a2c8c7d` (Section A6).

| Item | Configuration |
| --- | --- |
| Provider and endpoint | Gemini on Vertex AI, OpenAI-compatible Chat Completions, `global` endpoint |
| Default model | `gemini-3.5-flash-lite` (generally available); a comparison with `gemini-3.8-flash` (E2) was planned and closed on 19 November as not required |
| Model selection | Only from `configs/model.yaml` (tier); environment variables supply credentials and the project only |
| Temperature | 0 |
| Prompts | One file per prompt with a header (`id`, `version`, `purpose`, `inputs`, `output_schema`); the SHA-256 of the file is recorded with every call; user text inside `<user_question>`, retrieved content inside `<context>`, delimiter tags removed from values |
| Output validation | Each reply is validated against its Pydantic contract and a rule check (for example, identifiers must be among those retrieved, with a miscopied identifier repaired by its hash suffix; SQL must be one SELECT on the plan's table; every number in a narration must point to a result cell or a derived value; a decline or description may state no number absent from its sources). A reply cut at the cap or looping inside a field keeps its complete fields. One retry on a parse, validation or transient error; none on a non-transient provider error |
| Time-outs and rate limits | 20 s per request; an expired token is refreshed once; a rate-limit reply (429) is retried after 8 s, then 16 s |
| Call budget | At most 8 hosted-LLM calls per question, counted before each call |
| Thinking | Set per call purpose as `reasoning_effort`: route, SQL (first attempt), narration, clarification, decline and description `minimal`; intent, SQL repair and SQL regenerated after a failed result check `low` (regeneration was `medium` until 19 November, which took about 10 s) |
| Output cap | Per purpose for the visible reply: route 300, intent 1,024, SQL 1,024, SQL repair 1,024, narration 2,000, clarification 150, decline 800, description 1,200 tokens (each raised after a reply was cut off in a development run; reasons recorded in `configs/model.yaml`), plus an allowance per thinking level (minimal 0, low 1,024, medium 4,096, high 4,096), because thinking tokens count against the cap |
| Cost record | Input tokens and output tokens including thinking tokens, priced from `configs/model.yaml` (`gemini-3.5-flash-lite`: USD 0.30 input and 2.50 output per million tokens on the global endpoint, read on 16 November 2026) |

Choice of the endpoint (16 November 2026). Pay-as-you-go access to the 3.5 models is offered
on the `global`, `us` and `eu` endpoints, not in `asia-south1`. The global endpoint is priced
about 10% below the others and has the largest shared capacity. Requests may be processed in
any region; the agent sends public statistics and no personal data.

**Measured (17 November 2026): access and thinking check.** One small SQL-writing request per
model and thinking level, on the global endpoint, with the 512-token SQL cap
([`scripts/check_vertex.py`](../../scripts/check_vertex.py); results in
[`outputs/reports/`](../../outputs/reports/), files `check_vertex_2026-11-17_*.json`).

| Model | Thinking level | Latency | Reply tokens | Thinking tokens | Valid JSON | Cut at the cap |
| --- | --- | --- | --- | --- | --- | --- |
| `gemini-3.5-flash-lite` | minimal | 3.0 s | 115 | none reported | yes | no |
| `gemini-3.5-flash-lite` | medium | 3.4 s | 18 | 490 | no | yes |
| `gemini-3.5-flash` | low | 3.4 s | 133 | 302 | yes | no |
| `gemini-3.5-flash` | medium | 3.4 s | 74 | 423 | no | yes |
| `gemini-3.8-flash` | low | 3.6 s | 105 | none reported | yes | no |
| `gemini-3.8-flash` | medium | 6.1 s | 111 | 308 | yes | no |

Two consequences were applied before any agent run. Thinking tokens are reported outside
`completion_tokens` but are billed as output, so the cost record counts both (the Flash-Lite
result file predates this correction and under-states the cost of its medium call). Thinking
tokens also count against the output cap, so a thinking allowance is added to the cap per
level. Six calls, one per row; total cost about USD 0.013 (estimate from token counts).

**Measured (17 November 2026): prompt smoke tests against the live model.** These check the
prompts and the client, not the agent; the plans for SQL were written by hand in place of the
resolver.

| Test | Result | Change made because of it |
| --- | --- | --- |
| Intent extraction, 12 questions of the Milestone 3 set | First run stopped after 6 questions; after the fixes 11 of 12, then 12 of 12, every reply valid on the first call | Schema-enforced replies (`response_format: json_schema`); list fields repaired before validation; indicators retrieved per table; category values taken from the data; rule that a coarser place (a State on a market table) is a filter |
| SQL generation, 7 hand-built plans executed on DuckDB | 6 of 7 reached the expected figure; one repair fixed a misspelt column; rp-04 (30 monsoon seasons) was cut at the 512-token cap | Consecutive periods filtered as one range; SQL cap 1,024 tokens. Re-run of rp-04: 1098.84 over 30 rows (7 of 7) |

Commands: `python scripts/smoke_intent.py --yes`, `python scripts/smoke_sql.py --yes`. Outputs:
[`outputs/reports/`](../../outputs/reports/), files `smoke_intent_2026-11-17b.json`,
`smoke_sql_2026-11-17.json` and `smoke_sql_2026-11-17_rp04.json`. All checks to date used
about USD 0.07 of the cloud credit (estimate from token counts).

### A3. Tools and reliability checks

**Built (T4).** The deterministic tool layer now resolves places, periods, units and query plans;
provides calculations and bounded result-frame operations; validates intent-tied results; and
checks narrated numbers against executed evidence. The read-only SQL runner applies a 1 GB
memory limit, one DuckDB thread, disabled external access, a 10-second timeout, a 1,000-row cap,
and SQL column binding before execution. Live graph wiring is in
[`src/analyst/agents/tool_nodes.py`](../../src/analyst/agents/tool_nodes.py) and
[`src/analyst/agents/model_nodes.py`](../../src/analyst/agents/model_nodes.py). The targeted tool and
graph tests cover the deterministic tools and SQL runner. End-to-end data validation has been
carried out; a further round of validation is needed.

### A4. Experiments

**Harness built (T4).** [`src/analyst/evaluation/e2e_eval.py`](../../src/analyst/evaluation/e2e_eval.py)
creates the fixed 40/60 action-and-table stratified split, verifies gold SQL read-only, limits
parallel questions to two, retries provider 429 responses through the existing client, scores
the agent-level outcomes, and reports per-case predictions and repeat spread. The shared metric
implementations are in [`src/analyst/evaluation/metrics.py`](../../src/analyst/evaluation/metrics.py).
Split hashes and run targets are recorded in [`configs/evaluation.yaml`](../../configs/evaluation.yaml).
**Measured.** The experiment of Milestone 4 is the version ladder (Section A6): v0, v1 and v2
vary the retrieved context (catalogue only; guidance cards; verified examples) and the routing
backend (hosted LLM or Jev), with every other setting held fixed: catalogue top-k 4, the run
limits of Section A2, decision thresholds off, one model tier (`gemini-3.5-flash-lite`) and the
thinking levels and output caps of Section A2.x. Output caps, the request timeout and the run
deadline were set on the development set from cut-off replies and time-outs (reasons in
`configs/model.yaml` and `configs/agent.yaml`). Retrieval recall and MRR are reported in Section
1.2 (item 6).

### A5. Stability

**Framework built (T4).** Three-run scoring reports which case outcomes change across repeats,
with bootstrap intervals per run. **Measured:** run-to-run instability on `e2e_test` is 0.050 (v0)
and 0.083 (v1, v2), the share of questions scored correct in some runs and wrong in others; p95
latency varies from 10.5 to 17.1 s across the v0 runs and from 9.5 to 10.5 s across the v2 runs
(Section A6.2).

### A6. Results and error analysis

#### A6.1 Set-up

**Measured (19 November 2026).** All runs use one frozen commit, `a2c8c7d` on `docs/milestone-4`,
the hosted model `gemini-3.5-flash-lite` on the Vertex AI global endpoint (Section A2), and the
limits in [`configs/agent.yaml`](../../configs/agent.yaml) (at most 8 model calls and 45 seconds
per question). The three versions differ only in retrieved knowledge and in the routing backend:

| Version | Retrieved context | Tool and domain routing |
| --- | --- | --- |
| v0 | Catalogue entries of the top four tables | Hosted LLM |
| v1 | v0 plus guidance cards ([`guidance_cards.v3.json`](../../configs/rag/guidance_cards.v3.json)) | Hosted LLM |
| v2 | v1 plus verified question-and-SQL examples ([`rag_verified_examples.v2.jsonl`](../../data/sample/rag_verified_examples.v2.jsonl)) | Jev, with the hosted LLM as fallback ([`configs/inference.yaml`](../../configs/inference.yaml)) |

| Set | Items | Runs per version | Use |
| --- | --- | --- | --- |
| Development: `e2e_dev.v1` (40) and its supplement `e2e_dev_extra.v1` (20) | 60 | 1 | Configuration and fixes; the supplement adds describe, search and clarify items, which the 40-item split held too few of |
| Test: `e2e_test.v1` | 60 | 3 | Reported once, after the commit was frozen; never used for tuning |

Questions ran one at a time. The evaluation set requires validation and extension, in order to
enhance the agent and to test it extensively. The development set was used to find and fix
faults in the agent during the week, so development figures are optimistic.

**Scoring.** Scoring is deterministic: no language model judges the replies. The scorer compares
each saved prediction with its gold record, so scoring the same predictions again gives the same
figures and spends no credit. The only models in the loop are those of the agent under test
(`gemini-3.5-flash-lite`, and Jev for routing in v2). Code: `_case_success` and `_case_checks` in
[`src/analyst/evaluation/e2e_eval.py`](../../src/analyst/evaluation/e2e_eval.py).

| Expected action | A case is a success when |
| --- | --- |
| Answer | The agent answered; every gold value appears among the numbers of the result rows within a relative tolerance of 0.5%; the same values appear in the reply text (for a series of more than three values, its first and last); the expected places or categories appear in the result rows, alone or as a place with a category ("Bihar Rural"); and the agent's own number check passed |
| Clarify | The agent asked a question, and the slot it asked about (place, period, category) matches the missing slot named in the gold record |
| Decline | The agent declined, or replied that the request is out of scope |
| Describe or search | The agent took that path, and every gold table is among the tables it retrieved or named in its reply |

| Measure | Definition |
| --- | --- |
| Success | Share of cases that meet the rule of their expected action |
| Execution accuracy | Share of answer cases whose result rows contain the rows of the gold SQL, executed by the scorer on the same DuckDB tables; extra columns and rounding are allowed |
| Wrong-answer rate | Share of released answers that fail the success rule |
| Abstention precision and recall | Precision and recall of the agent's non-answers (decline, clarify, abstain) against the cases whose gold expects a decline or a clarification |
| Run-to-run instability | Share of questions scored correct in some runs and wrong in others |

Two limits follow from deterministic scoring. Wording is not judged: a reply with every correct
number and awkward phrasing passes, so wording faults are listed separately (Section A6.5). Labels
are read literally: in e2e-031 the gold names the missing slot "State", which the scorer reads as
the geographic level, while the agent asks which of two districts named Aurangabad is meant, a
place question with Bihar and Maharashtra as options; the case is scored as a failure.

#### A6.2 Results

Test set, mean over three runs (minimum to maximum)
([`version_ladder_test.md`](../../outputs/reports/version_ladder_test.md)):

| Measure | v0 | v1 | v2 |
| --- | --- | --- | --- |
| Success | 0.683 (0.667 to 0.700) | 0.689 (0.667 to 0.700) | 0.694 (0.667 to 0.717) |
| Success, 95% interval of the first run | 0.55 to 0.80 | 0.58 to 0.82 | 0.60 to 0.82 |
| Execution accuracy | 0.433 (0.425 to 0.450) | 0.525 | 0.633 (0.625 to 0.650) |
| Wrong-answer rate | 0.038 (0.037 to 0.038) | 0.012 (0.000 to 0.037) | 0.083 (0.069 to 0.107) |
| Abstention precision | 0.610 (0.591 to 0.619) | 0.544 (0.542 to 0.545) | 0.568 (0.522 to 0.591) |
| Abstention recall | 1.000 | 0.949 (0.923 to 1.000) | 0.974 (0.923 to 1.000) |
| Latency p50 (s) | 6.9 (6.7 to 7.1) | 6.7 (6.4 to 6.9) | 6.0 (5.8 to 6.5) |
| Latency p95 (s) | 13.0 (10.5 to 17.1) | 11.9 (10.4 to 13.6) | 10.0 (9.5 to 10.5) |
| Cost per answered question (USD, estimate) | 0.0269 | 0.0296 | 0.0190 |
| Model calls per answered question | 8.75 | 8.56 | 6.05 |
| Run-to-run instability | 0.050 | 0.083 | 0.083 |

Success by expected action on the test set, all runs pooled (cases in brackets):

| Expected action | v0 | v1 | v2 |
| --- | --- | --- | --- |
| answer | 0.642 (120) | 0.667 (120) | 0.650 (120) |
| clarify | 0.444 (18) | 0.278 (18) | 0.278 (18) |
| decline | 1.000 (21) | 1.000 (21) | 1.000 (21) |
| describe | 0.667 (12) | 0.750 (12) | 1.000 (12) |
| search | 1.000 (9) | 1.000 (9) | 1.000 (9) |

Development set, one run per version
([`version_ladder_dev.md`](../../outputs/reports/version_ladder_dev.md)):

| Measure | v0 | v1 | v2 |
| --- | --- | --- | --- |
| Success | 0.933 | 0.917 | 0.967 |
| Execution accuracy | 0.703 | 0.703 | 0.865 |
| Wrong-answer rate | 0.029 | 0.029 | 0.000 |
| Cost per answered question (USD, estimate) | 0.0220 | 0.0227 | 0.0174 |
| Model calls per answered question | 7.09 | 7.06 | 5.17 |

The twelve runs cost about USD 8.3 of the cloud credit (estimate from token counts: development
USD 2.2, test USD 6.2).

#### A6.3 Reading of the results

1. **Execution accuracy rises with each version on the test set**, from 0.433 (v0) to 0.525 (v1)
   and 0.633 (v2), with little spread between runs. Guidance cards and verified examples help the
   model write the correct query once the question reaches the query path.
2. **Success is flat across versions** (0.683 to 0.694; the intervals overlap). The failures that
   limit success arise before the query is written, mainly in place resolution (Section A6.4),
   and no version changes that step.
3. **v2 is the cheapest and fastest version**: about 30% lower cost per answered question than v0,
   2.7 fewer model calls, and a p95 latency of 10.0 s against 13.0 s, because Jev replaces the
   routing call to the hosted model.
4. **v2 gives more wrong answers than v1** (0.083 against 0.012). The difference comes from two
   items: a follow-up that asked for a five-year series received only its end points and their
   change (e2e-076, all three runs), and in one run the narration of a comparison follow-up left
   out one of its two values (e2e-004).
5. **The development set over-states quality** by 0.25 to 0.27 success: 0.93 to 0.97 on
   development against 0.68 to 0.69 on test. The development set was used for fixes; the test
   figures are the ones to quote.
6. **Declines and searches are reliable** (1.000 in every version). Clarification is the weakest
   action (0.28 to 0.44), for the reasons in Section A6.4.

#### A6.4 Error analysis (test set)

The test items were read only after the runs, to classify failures; no change was made from
them. In each version 21 distinct items fail in at least one run; across the three versions,
26 items fail at least once. Grouped by cause:

| Cause | Items | Versions affected | What happens |
| --- | --- | --- | --- |
| Place resolution | e2e-015, 016, 020, 029, 035, 040 | All | A State is not mapped to its IMD rainfall sub-divisions (Karnataka; Odisha to "Orissa"; Delhi to "Haryana Delhi & Chandigarh"); a mandi name is not matched to its listed name (Azadpur to "APMC Azadpur"); an urban-rural question on a State is asked about; a State named with a district ("Aurangabad, Maharashtra") is not used to choose between two districts of that name. The agent asks or declines instead of answering |
| Periods | e2e-039, 041, 092 | All | "Right now" is declined instead of taking the latest period; a question is asked with a single period option; a value suppressed by the publisher ends in a period question or an abstention |
| Calculation and checks | e2e-006, 055, 097, 098, 099 | All but e2e-098 (v0 and v1 only) | The national total row is excluded before a comparison with it; a State's share of the India total fails the result check; one request reaches the limit of 8 model calls; one answer in bales fails the number check |
| Clarification slot or content | e2e-031, 044 | All | The agent asks which Aurangabad (a place) where the gold note names the slot as "State"; for a price question the agent asks for the market where the gold asks for the commodity |
| Expected action disputed | e2e-008, 013 | All | Gold expects a clarification; the agent declines with a correct reason (calendar-year figures cannot be derived from July-June survey years; the participation table is urban only). Both are referred to the validation of the set; the gold is not changed |
| Follow-up scope | e2e-076, 004, 071 | v2 (076, 004), v1 (071) | A series follow-up is answered with its end points only (e2e-076, every v2 run); a comparison follow-up states or returns only one of its two values (e2e-004 and e2e-071, one run each) |
| Missing place, then a provider error | e2e-021 | v1 (two runs), v2 (one run) | A rainfall question without a place is sent to the query path instead of being asked about, and the run ends in a provider error |
| Describe or search routed elsewhere | e2e-026, 049 | v0, v1 | A describe question is answered with a catalogue search |
| Single-run failures | e2e-037, 056 | v2, v0 | A narration that does not state the value it was given ends in abstention (e2e-037); one runner exception (e2e-056) |

Place resolution is the largest cause and affects every version equally, which explains why
success does not follow execution accuracy. The fixes are general (State to sub-division mapping,
market-name aliases, use of a stated State to choose among same-named districts, "now" as the
latest period, no question with one option). They will be developed on new development items of
the same kinds, never on the test items, and measured with v3 in the following week.

#### A6.5 Sample outputs

Replies of v2, first test run, copied from
[`final_test_v2_r1.jsonl`](../../outputs/predictions/final_test_v2_r1.jsonl):

| Item | Question | Reply |
| --- | --- | --- |
| e2e-065 (answer with a derivation) | By what percent did Karnataka's per capita GSDP grow from 2019-20 to 2022-23? | "Karnataka's per capita GSDP at current prices grew by 37.55 percent from fiscal year 2019-20 to fiscal year 2022-23, according to the Per capita GSDP (rupees) at current prices, 28 States, 2019-20 to 2023-24 dataset by Rajya Sabha answer on data.gov.in." |
| e2e-018 (follow-up) | Same for the 2017 monsoon season. | "During the 2017-JJAS season, Vidarbha received 731.5 millimeters of rainfall, according to the IMD rainfall (mm) by month, season and year for 36 meteorological sub-divisions dataset." |
| e2e-073 (clarification) | What is the MSP of cotton in 2023-24? | "Please specify whether you are looking for the MSP of Long Staple or Medium Staple cotton. Options: 1. Long Staple; 2. Medium Staple." |
| e2e-080 (decline) | How has urban labour force participation changed over the last five years? | "The catalogue does not contain the requested data. Missing: period (The PLFS urban LFPR table only covers the survey year 2023-24 and does not contain data for the last five years). Related tables: plfs_lfpr_urban_state, plfs_state_ur_usual_status. The request has been recorded as a data request." |
| e2e-049 (description) | Is the national crime data broken down by state? | "The table 'NCRB national crime incidence and rates, 2022-2024' (CII 2024 Table 1.1(ii)) provides national totals only and contains no State or district breakdown." |

The figures in these replies are correct, but the wording has faults that the success measure
does not score: period labels repeated beside values ("2020-21 19.2, 2020-21 13.4" in e2e-002),
the MSP crop year described as a "July-June survey year" (e2e-069), a default-period note joined
awkwardly to the sentence (e2e-009) and source names copied in full. Narration wording is
reviewed with v3.

#### A6.6 Limitations

- 60 test items give wide intervals (about plus or minus 0.12 on success); differences of one
  point between versions are not separable.
- The evaluation set requires validation and extension to enhance the agent and to test it
  extensively; two expected actions are disputed (Section A6.4).
- One hosted model tier was run; the two-tier comparison (E2) was closed as not required (Section 1.2).
- Verification is pass-through in v0 to v2, so the confidence badge reads "not verified" on every
  answer; calibrated verification arrives with v5.

#### A6.7 Reproduction

From the repository root at commit `a2c8c7d`, with Vertex AI credentials and `TYPESAFE_API_KEY`
(for Jev in v2) set, for each version `v` in v0, v1, v2:

```bash
python -m analyst.evaluation.e2e_eval run --live --yes --allow-unvalidated --workers 1 \
    --version v2 --experiment final_test_v2_r1 --member T3 \
    --set data/eval/e2e_test.v1.jsonl --out outputs/predictions/final_test_v2_r1.jsonl
python -m analyst.evaluation.e2e_eval score \
    --predictions outputs/predictions/final_test_v2_r{1,2,3}.jsonl \
    --out outputs/reports/final_test_v2.json
python scripts/version_ladder.py --set test --rows v0=outputs/reports/final_test_v0.json \
    v1=outputs/reports/final_test_v1.json v2=outputs/reports/final_test_v2.json \
    --out outputs/reports/version_ladder_test
```

The development runs use `--set data/eval/e2e_dev.v1.jsonl data/eval/e2e_dev_extra.v1.jsonl`.
Predictions: [`outputs/predictions/`](../../outputs/predictions/), files `final_dev_*` and
`final_test_*`; score reports and tables: [`outputs/reports/`](../../outputs/reports/), files
`final_*.json` and `version_ladder_*`.

## Part B. The decision models

Part B follows the twelve headings of the Milestone 4 guideline. Protocol, fixed before any
planned run was trained and before the `dev_human` labels were frozen:
[`docs/specs/kev_training_protocol.md`](../../docs/specs/kev_training_protocol.md) (version 1.1).
Every figure below is **Measured** unless tagged otherwise, and names the committed file that
holds it.

### B1. Introduction

Phase 1 of the Kev adoption (decision of 5 November) puts one control decision of the agent on a
fine-tuned decision model: the **domain** of a user message, a closed choice among eight labels
(`labour`, `agriculture`, `rainfall`, `prices_economy`, `health`, `other`, `multiple`,
`unspecified`). The domain ranks retrieval; it never filters it. Tool selection stays on Jev until
phase 2. The model is Kev-0.8B: the base language model `Qwen/Qwen3.5-0.8B-Base` with a LoRA
adapter and a pointer head that scores the options of a question. Kev is fine-tuned on our routing
data, calibrated by temperature scaling, and adopted only if it passes a gate fixed in advance
against Jev, the hosted decision model used as the reference: accuracy within 3 points of Jev and
expected calibration error (ECE) at most 0.10 after calibration, both on human labels.

Outcome in one line: the selected run `ep3` scores 0.980 accuracy on the 198 human-labelled test
items against 0.783 for Kev zero-shot and 0.970 for Jev; the gate passes; at a 5% error budget the
cascade leaves every item with Kev (Section B12).

### B2. Training dataset

**Built.** The domain files are derived from routing data v2 (`data/splits/kev/*.v2.jsonl`,
tracked) by `python scripts/build_domain_phase1.py --version v2 --laya`. Hashes:
[`data/MANIFEST.md`](../../data/MANIFEST.md) and [`configs/train.yaml`](../../configs/train.yaml);
`python -m analyst.models.kev_runs check-data` compares local files with them.

| Split | Records | Labels | Use |
| --- | --- | --- | --- |
| `train.v2` | 1,876 | Rules 1,287; paraphrases 324; teacher model 265 | Training |
| `calibration.v2` | 322 | Rules and teacher, checked by hand | Temperature fit; validation loss |
| `dev_synthetic.v2` | 355 | Rules and teacher, checked by hand | Checkpoint selection |
| `dev_human.v1` | 198 | Human, two labellers per item and an adjudicator | Test set, scored once |

Each record is a router state (the top-4 catalogue candidates, the conversation context and the
message) and one choice question with the eight domain options. Augmentation is applied on the
fly by `kev.train` and does not change the files (Section B8).

**Coverage** ([`kev_data_coverage_v2.md`](../../outputs/reports/kev_data_coverage_v2.md),
`python -m analyst.models.kev_report coverage`). Every one of the 14 catalogue tables appears in
every split. All eight labels are present in every split; in train the shares range from 5.0%
(`multiple`) to 31.8% (`labour`), and `labour` and `rainfall` together make up 57%. The skew is
reported, not reweighted; per-label F1 keeps minority labels visible. Census 2011 is not in the
published catalogue and is not covered.

**State length** ([`kev_state_lengths_v2.json`](../../outputs/reports/kev_state_lengths_v2.json)):
median 248 and maximum 318 Qwen tokens, below `--max_state 384`; no record is dropped or
truncated.

**Test set `dev_human`.** See Section 2.3. It was never used for training, selection, tuning or
calibration.

### B3. Model configuration

**Built.** [`configs/train.yaml`](../../configs/train.yaml); Kev source at commit `2074cc44`.

| Item | Value | Source |
| --- | --- | --- |
| Base model | `Qwen/Qwen3.5-0.8B-Base`, revision `dc7cdfe2` | `configs/train.yaml` |
| Warm start | `jaredpalmer/kev-0.8b@bf75a6a8…` (released Kev-0.8B: LoRA rank 16, pointer head 256). `kev.train` has no revision flag, so the revision is part of the `--init_from` value; the resolved snapshot is recorded per run (`init_source`) | `kev/checkpoint.py:38-45` |
| Adapter | LoRA rank 16, alpha 32, dropout 0.05, all linear modules | `kev/model.py:274` |
| Output | Pointer head over the options; softmax over the eight options | Kev |
| Calibration | One temperature per run, fitted on `calibration` by NLL, applied unchanged to dev and test | `src/analyst/evaluation/decision_eval.py` |

Under `--init_from`, the LoRA rank, head dimension and base revision must equal those of the
released checkpoint (`kev/checkpoint.py`, `COMPAT_FIELDS`). A different rank is possible only from
the base model; the one from-base run (`base_r16`) therefore measures the value of the warm start.

### B4. Training environment

**Measured** ([`outputs/reports/kev_runs/<run>/environment.json`](../../outputs/reports/kev_runs/)
and `pip_freeze.txt` per run).

| Item | Value |
| --- | --- |
| Hardware | Kaggle, two Tesla T4 GPUs per session (16 GB each; one run per GPU); Colab, one Tesla T4 (`base_r16`) |
| Software | Python 3.13.16, PyTorch 2.8.0+cu128 (CUDA 12.8), transformers 5.17.0, peft 0.21.0; locked with `uv sync --python 3.13 --frozen --no-dev` |
| Precision | fp32 weights and compute: `kev.train` offers fp32 or bf16 only, and the T4 has no bf16 |
| Memory and time | Peak GPU memory 6.7-6.8 GB; about 0.56 s per record; 17.6 min (1 epoch) to 53.0 min (3 epochs) per run |
| Notebook | [`notebooks/kev_train_t4.ipynb`](../../notebooks/kev_train_t4.ipynb): checks CUDA and disk before downloading, finds the data by SHA-256, runs one queue per GPU, validates and saves each run as soon as it ends |
| Scoring backend | One local machine (Apple M5, 16 GB, MPS) for every run, so accuracy and ECE come from one backend |

Reproducibility: the three T4 smoke runs (Colab and both Kaggle GPUs) saved byte-identical
adapters and the same loss (0.906 at step 10); the records are in
[`outputs/reports/kev_runs/smoke_colab/`](../../outputs/reports/kev_runs/smoke_colab/).

### B5. Training methodology

1. **Smoke run per platform** (32 records, 16 optimizer steps): exit code 0, a loss line, and all
   output files written.
2. **Planned runs** on Kaggle and Colab from `python -m analyst.models.kev_runs plan` (sessions
   `kaggle_1` to `kaggle_3` and `colab_1` in `configs/train.yaml`).
3. **Scoring** of each checkpoint on `calibration` and `dev_synthetic`:
   `scripts/score_kev_run.sh <run>`; output `outputs/reports/score_domain_<run>.json`.
4. **Registration**: `python -m analyst.models.kev_runs register …` updates
   [`models/registry.json`](../../models/registry.json) and archives the run records.
5. **Selection** by the rule of Section B10, then **one** score on the frozen `dev_human`, the gate
   and the cascade (protocol Section 6).

Loss: cross-entropy over the options' pointer logits (`kev/train.py:41-61`). The comparison is one
factor at a time from the base configuration B0: learning rate 2e-5, 2 epochs, batch 1 with
gradient accumulation 8 (effective batch 8), warm start, seed 0.

### B6. Hyperparameter experiments

Eight runs were planned and trained. The protocol set five further runs (training-set size 250,
500 and 1,000; LoRA rank 8 and 32 from the base model) as conditional on remaining compute.
Compute remained, but they were not run: the eight runs met the selection rule, with the seed
spread as noise floor, and the selected run then passed the gate on human labels (Section B12).
The next test of the domain decision is inside the agent, in the end-to-end evaluation. The
deferred runs are kept as an option if that evaluation shows domain errors caused by the model.
The training-set-size runs then measure how much data the decision needs, and the rank runs
measure whether capacity limits it. Source:
[`kev_runs_table.md`](../../outputs/reports/kev_runs_table.md)
(`python -m analyst.models.kev_report table`); `dev` is `dev_synthetic` (355 items); NLL and ECE
after the run's temperature.

| Run | Varies | lr | Epochs | Seed | Minutes | Dev accuracy | Dev macro-F1 | Dev NLL | Dev ECE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `b0_s0` | B0 | 2e-5 | 2 | 0 | 35.1 | 0.992 | 0.986 | 0.035 | 0.013 |
| `b0_s1` | Seed | 2e-5 | 2 | 1 | 34.6 | 0.992 | 0.986 | 0.037 | 0.020 |
| `b0_s2` | Seed | 2e-5 | 2 | 2 | 35.2 | 0.992 | 0.986 | 0.053 | 0.016 |
| `lr1e-05` | Learning rate | 1e-5 | 2 | 0 | 35.8 | 0.986 | 0.979 | 0.076 | 0.037 |
| `lr4e-05` | Learning rate | 4e-5 | 2 | 0 | 34.6 | 0.994 | 0.991 | 0.025 | 0.007 |
| `ep1` | Epochs | 2e-5 | 1 | 0 | 17.6 | 0.966 | 0.948 | 0.140 | 0.055 |
| `ep3` | Epochs | 2e-5 | 3 | 0 | 53.0 | 0.994 | 0.991 | 0.024 | 0.009 |
| `base_r16` | From base model | 2e-4 | 2 | 0 | 37.0 | 0.989 | 0.980 | 0.033 | 0.006 |
| Kev zero-shot | Reference | - | - | - | - | 0.823 | 0.626 | 0.621 | 0.074 |

Findings: a lower learning rate (1e-5) and a shorter horizon (1 epoch) under-train; a higher rate
and a longer horizon give the best validation NLL. The three B0 seeds give identical accuracy and
an NLL range of 0.035 to 0.053, which is the noise floor of Section B10. Batch size and scheduler
were not varied: the effective batch is fixed at 8 and the OneCycle schedule is a constant of
`kev.train`.

### B7. Optimization methods

AdamW with weight decay 0.01 on the LoRA and head parameters (`kev/train.py:377`, `:580`);
OneCycle learning-rate schedule with 10% warm-up over all optimizer steps (`:588`); global
gradient-norm clipping at 1.0 (`:632`). The share of clipped optimizer steps per run is in
`kev_runs_table.md`: 0.33 (`ep3`) to 0.77 (`ep1`); B0 0.44-0.45; lower learning rate 0.71. Runs
with more optimizer steps have a lower share.

Early stopping: `kev.train` saves per-epoch snapshots only for full-weight training, and a LoRA
run cannot resume. `ep1`, B0 and `ep3` are therefore separate runs, each with a OneCycle schedule
over its own length. They compare training horizons and are not reported as early stopping.

### B8. Regularization

| Method | Setting |
| --- | --- |
| Low-rank adaptation | Rank 16; the base model stays frozen |
| LoRA dropout | 0.05 |
| Weight decay | 0.01 |
| Data augmentation, on the fly per record and epoch (`kev/data.py:320-343`) | Option order always shuffled; a 'none' option added as a wrong alternative with probability 0.12; an unrelated option with probability 0.15; label replacement by 'none of the above' switched off (`--p_none 0`), since serving never offers that option |
| Paraphrased records | 324 of the 1,876 training records |
| Not used | Label smoothing, class weights, cross-validation (three seeds instead) |

Overfitting check: the training loss of the longer runs approaches zero (final 10-step mean 0.001
for `ep3` and `lr4e-05`), but validation NLL keeps falling with the horizon (Section B9), and the
test accuracy on human labels (0.980) is close to the validation accuracy on `dev_synthetic`
(0.994). The fitted temperatures (2.6 to 3.9) show that the raw probabilities are over-confident
on the calibration split. On the evaluation sets the effect of scaling is mixed for the selected
run: it lowers NLL (`dev_human` 0.081 to 0.070) but raises ECE (0.017 to 0.040; `dev_synthetic`
0.005 to 0.009). Both ECE values are well below the 0.10 limit; the gate uses the calibrated value,
as fixed in advance (Section B12).

### B9. Training progress

Training loss every 10 steps, all runs:
[`kev_train_loss.png`](../../outputs/figures/kev_train_loss.png) (data
[`kev_train_loss.csv`](../../outputs/reports/kev_train_loss.csv)). Validation loss against the
training horizon: [`kev_validation_by_epoch.png`](../../outputs/figures/kev_validation_by_epoch.png)
([`kev_validation_by_epoch.json`](../../outputs/reports/kev_validation_by_epoch.json)); command
`python -m analyst.models.kev_report curves`.

| Horizon (run) | Calibration NLL, raw | Dev NLL, after temperature | Dev accuracy |
| --- | --- | --- | --- |
| 1 epoch (`ep1`) | 0.349 | 0.140 | 0.966 |
| 2 epochs (`b0_s0`) | 0.254 | 0.035 | 0.992 |
| 3 epochs (`ep3`) | 0.234 | 0.024 | 0.994 |

`kev.train` measures no validation loss during LoRA training; validation NLL is measured on each
saved checkpoint.

### B10. Model selection

Rule, fixed in the protocol before any `dev_human` score: the temperature of each run is fitted on
`calibration`; the checkpoint with the lowest `dev_synthetic` NLL after temperature is selected,
macro-F1 breaking ties; only planned runs compete; a setting other than B0 is selected only if its
NLL is below the mean of the three B0 seeds by more than their range, otherwise the best B0 seed is
kept. This is a conservative range heuristic, not a significance test. Implementation:
`python -m analyst.models.kev_report select`; output
[`kev_selection.json`](../../outputs/reports/kev_selection.json), committed before the test set was
scored.

| Quantity | Value |
| --- | --- |
| B0 seeds, dev NLL | 0.0351, 0.0371, 0.0525 |
| Mean and range | 0.0416 and 0.0175; threshold 0.0241 |
| Best other setting | `ep3`, 0.0237 (below the threshold by 0.0004) |
| Next | `lr4e-05`, 0.0253 (above the threshold) |
| **Selected** | **`ep3`** |

`ep3` and `lr4e-05` are close; the fixed rule decides between them. The selected checkpoint is
registered in [`models/registry.json`](../../models/registry.json); weights are kept on the shared
drive (`Group4/checkpoints/ep3`), not in git.

### B11. Challenges

The full log is protocol Section 8; the main items:

| Issue | Handling |
| --- | --- |
| No fp16 in `kev.train` and no bf16 on the T4 | All runs in fp32 |
| LoRA rank fixed by the warm start | Rank runs only from the base model; two of them deferred |
| No validation loss during LoRA training; no resume | Validation on each saved checkpoint; horizon runs instead of early stopping; runs under one hour |
| Free compute: one account per platform per person | The eight runs fitted within the free-tier sessions, two GPUs at a time on Kaggle; the five deferred runs were not needed (Section B6) |
| External code review (17 November): unpinned warm start, augmentation defaults, from-base learning rate, run persistence, strict evaluation checks | All valid findings fixed before the planned runs; protocol Section 9 |
| Laya, the planned comparator, ran out of memory on the local machine (its internal evaluation uses a fixed batch of 16) | Kev was taken forward because its zero-shot accuracy on `dev_synthetic` was well above Laya's: 0.823 against 0.473 ([`score_domain_zeroshot_v2.json`](../../outputs/reports/score_domain_zeroshot_v2.json), [`score_domain_laya_zeroshot_v2.json`](../../outputs/reports/score_domain_laya_zeroshot_v2.json)). A fine-tuned Laya run on a Kaggle T4 (notebook prepared) is planned for the following week |
| Scoring of one batch took about 7 hours instead of about 45 minutes, most likely because the local machine slept | Later scoring runs keep the machine awake (`caffeinate`) |
| Labelling: one labeller's file used non-option names (`economy`, `missing`) | Corrected for format only, mapped by the labeller's own cited rule, and confirmed by the labeller; recorded in the `dev_human` README |
| Tool-selection agreement below target (Cohen's kappa 0.70 against 0.80) | Every disagreement adjudicated; reported. The domain decision, the one trained here, has kappa 0.88 |
| Before adjudication, a provisional score of `ep3` against one labeller's labels (133 items) was taken, after the selection was committed | It changed no decision; the reported test score is the single score on the frozen set |

### B12. Summary

Test set: frozen `dev_human`, 198 items (Section 2.3). Kev rows are scored on the local machine;
Jev through its hosted API (latency includes the network). Accuracy with a bootstrap 95% interval;
NLL, Brier and ECE after the temperature fitted on `calibration`.

| Model | Accuracy (95% CI) | Macro-F1 | NLL | Brier | ECE raw / calibrated | AUROC of correctness | Latency p50 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Kev-0.8B zero-shot | 0.783 (0.727-0.838) | 0.625 | 0.754 | 0.350 | 0.068 / 0.081 | 0.777 | 0.57 s |
| **Kev-0.8B fine-tuned (`ep3`)** | **0.980 (0.960-0.995)** | **0.973** | **0.070** | **0.034** | 0.017 / **0.040** | **0.978** | 0.57 s |
| Jev (reference) | 0.970 (0.944-0.990) | 0.962 | 0.102 | 0.047 | 0.033 / 0.034 | 0.905 | 0.34 s |

Sources: [`score_domain_ep3_dev_human.json`](../../outputs/reports/score_domain_ep3_dev_human.json),
[`score_domain_zeroshot_v2_dev_human.json`](../../outputs/reports/score_domain_zeroshot_v2_dev_human.json),
[`score_domain_jev_dev_human.json`](../../outputs/reports/score_domain_jev_dev_human.json);
reliability diagrams `outputs/figures/reliability_domain_<run>_dev_human.png`.

Per-label F1 of `ep3` ranges from 0.91 (`multiple`, 12 items) to 1.00; zero-shot Kev scores 0 on
`multiple` and `unspecified`, the two labels that depend on the project's own conventions.

**Gate: passed** ([`gate_domain.json`](../../outputs/reports/gate_domain.json)). Kev minus Jev
accuracy +1.0 point (95% CI -2.0 to +3.5) against a margin of 3 points; the point estimate decides
(`configs/inference.yaml`), and the non-inferiority test (lower bound above -3 points) also passes.
Kev ECE after calibration 0.040 against a limit of 0.10.

**Cascade** ([`cascade_domain.json`](../../outputs/reports/cascade_domain.json)). At a 5% error
budget, the confidence threshold set on `calibration` is 0.446 (error on the 322 accepted items
1.6%, one-sided 95% upper bound 3.2%). On `dev_human`, Kev handles 100% of the items with an error
of 2.0%, and no call is escalated to Jev. Cost per 1,000 decisions is unknown, because the Jev API
does not report it.

**Option-order robustness** ([`flips_domain_ep3_dev_human.json`](../../outputs/reports/flips_domain_ep3_dev_human.json)):
across three option orders, 1 of 198 predictions changes (flip rate 0.5%).

**Conclusion.** Fine-tuning raises Kev-0.8B from 0.783 to 0.980 accuracy on human labels for the
domain decision and brings its calibrated ECE to 0.040. It matches Jev within the pre-set margin;
its lead of one point is not statistically separable from Jev. Under the adoption rule, the domain decision moves to
Kev, with the cascade to Jev kept for items below the threshold. Limits: one decision, one test set of
198 items written by T3 and labelled by the team, five conditional runs not run (Section B6), no fine-tuned
Laya row yet (planned for the following week), no row for the v0 hosted LLM on this decision, and no held-out-table split (deferred in
`configs/train.yaml`).

## 3. Drift baseline and log collation

**Built (T4).** Run bundles use a versioned manifest with row counts and file hashes;
[`src/analyst/ops/collate_runs.py`](../../src/analyst/ops/collate_runs.py) validates bundles,
deduplicates imports and records conflicting rows without overwriting them. The offline drift
report in [`src/analyst/ops/drift.py`](../../src/analyst/ops/drift.py) compares outcome, routing,
confidence, result-check, repair, cost and latency signals, with minimum window sizes and human
review suggestions. No real baseline or simulated-shift report is claimed because the evaluation
runs and collated warehouse are not yet available.

## 4. Key findings

**Agent system (Part A; `e2e_test`, 3 runs x 60 questions; detail in Section A6).**

1. Execution accuracy rises with each version: 0.433 (v0), 0.525 (v1) and 0.633 (v2). Guidance
   cards and verified examples help the model write the correct query.
2. End-to-end success is flat (0.683 to 0.694; the intervals overlap). The failures that limit it
   arise before the query is written, mainly in place resolution (State to IMD sub-division,
   market aliases), which no version changes (Section A6.4).
3. v2 is the cheapest and fastest version: about 30% lower estimated cost per answered question
   than v0, 2.7 fewer model calls and a p95 latency of 10.0 s against 13.0 s, because Jev
   replaces the routing call to the hosted model.
4. Declines and searches are reliable (1.000 in every version); clarification is the weakest
   action (0.28 to 0.44). The development set over-states quality (success 0.92 to 0.97 against
   0.68 to 0.69 on test); the test figures are the ones to quote.

**Decision models (Part B; `dev_human`, 198 items).**

5. Fine-tuning moves Kev-0.8B on the domain decision from 0.783 to 0.980 accuracy, and from
   macro-F1 0.625 to 0.973. The largest change is on the two labels defined by the project's own
   conventions, `multiple` and `unspecified` (F1 0 for zero-shot Kev).
6. The fine-tuned model is well calibrated with or without temperature scaling (ECE 0.017 raw,
   0.040 scaled, against a limit of 0.10). Scaling lowers NLL but slightly raises ECE on the test
   set; the temperatures fitted on the calibration split (2.6 to 3.9) over-correct for it.
7. Fine-tuned Kev matches Jev within the pre-set margin (difference +1.0 point, 95% CI -2.0 to
   +3.5); the gate passes, and at a 5% error budget the cascade keeps every item on Kev.
8. Validation on rule- and teacher-labelled data (0.994) predicts the human-labelled result
   (0.980) well for this decision. Human agreement is high for the domain (kappa 0.88) and lower
   for tool selection (0.70), which is the harder decision for phase 2.

**Next.** Fix the general failure causes of Section A6.4 (place resolution, periods,
clarification) through new development items, never through test text, and measure them with v3
(prompt optimisation); put Kev on the domain decision inside the agent (v4) and measure it on
`e2e_test`; fine-tune Laya and report it beside Kev.

## Appendix A. Artifacts and reproduction

Every command runs from the repository root. Model weights and the raw and processed tables are
not in git; the checkpoints are on the shared drive (`Group4/checkpoints/<run>`), and the data
files are checked against their hashes before use.

**Part B: decision models.**

| Step | Command | Output |
| --- | --- | --- |
| Build the domain files | `python scripts/build_domain_phase1.py --version v2 --laya` | `data/splits/kev_domain/*.v2.jsonl` (hashes in `data/MANIFEST.md`) |
| Check the data | `python -m analyst.models.kev_runs check-data` | Pass or fail against `configs/train.yaml` |
| Coverage | `python -m analyst.models.kev_report coverage` | `outputs/reports/kev_data_coverage_v2.{json,md}` |
| Run plan | `python -m analyst.models.kev_runs plan` | `kev_plan.json` (runs, commands, data hashes) |
| Train | [`notebooks/kev_train_t4.ipynb`](../../notebooks/kev_train_t4.ipynb), `PLATFORM` and `SESSION` set per `configs/train.yaml` | `checkpoints/<run>/` with `environment.json`, `train.log`, `pip_freeze.txt` |
| Score a run | `scripts/score_kev_run.sh <run>` | `outputs/reports/score_domain_<run>.json`, predictions, reliability figure |
| Register a run | `python -m analyst.models.kev_runs register models/checkpoints/<run> --run-id <run> --drive-path Group4/checkpoints/<run> --scores outputs/reports/score_domain_<run>.json` | [`models/registry.json`](../../models/registry.json), `outputs/reports/kev_runs/<run>/` |
| Comparison, curves, selection | `python -m analyst.models.kev_report table`, `curves`, `select` | `kev_runs_table.md`, `kev_train_loss.png`, `kev_validation_by_epoch.png`, `kev_selection.json` |
| Freeze `dev_human` | `python scripts/label_agreement.py agree`, then `freeze --items data/labels/dev_human_v1/items_rendered.jsonl` | `agreement.json`, `freeze.json`, `data/splits/kev/dev_human.v1.jsonl` |
| Test records | `python scripts/build_domain_phase1.py --dev-human data/splits/kev/dev_human.v1.jsonl` | `data/splits/kev_domain/dev_human.v1.jsonl` |
| Test scores | `SPLITS=dev_human scripts/score_kev_run.sh ep3`; `SPLITS=dev_human scripts/score_kev_run.sh zeroshot_v2 released`; Jev, gate and cascade as in [`kev_training_protocol.md`](../../docs/specs/kev_training_protocol.md) Section 6 | `score_domain_*_dev_human.json`, `gate_domain.json`, `cascade_domain.json` |
| Option order | `decision_eval run --option-order-seed 1` and `2`, then `decision_eval flips` | `flips_domain_ep3_dev_human.json` |

Pinned versions: Kev commit `2074cc44`; base model revision `dc7cdfe2`; warm start
`jaredpalmer/kev-0.8b@bf75a6a8`; environment locked by `uv sync --python 3.13 --frozen --no-dev`.

**Part A: agent system.** Configuration files in [`configs/`](../../configs/); evaluation harness
[`src/analyst/evaluation/e2e_eval.py`](../../src/analyst/evaluation/e2e_eval.py); ladder tables
from [`scripts/version_ladder.py`](../../scripts/version_ladder.py), output
[`version_ladder_test.md`](../../outputs/reports/version_ladder_test.md) and
[`version_ladder_dev.md`](../../outputs/reports/version_ladder_dev.md). Run, score and ladder
commands: Section A6.7.

## Contribution log

Milestone 4 work per member; the weekly record with links is in [`WORKLOG.md`](../../WORKLOG.md),
and the commits are on `docs/milestone-4`.

| Member | Track | Milestone 4 contribution | Report sections |
| --- | --- | --- | --- |
| Shaoni Samanta (21f1003157) | T1 Data and Tools | Seven T1 tables configured and published (crop production with per-crop units), data manifest; the end-to-end evaluation set `e2e_v1` (100 questions); `dev_human` labelling and adjudication | 2.1, 2.2 |
| Shivanshu Gupta (22f3002985) | T2 Agent | Contracts package, graph and control nodes, memory and run log, fixes to the agent workflow; `dev_human` labelling and adjudication | A1, A2 |
| Sathya Prakash (21f1006001) | T3 Model | Hosted LLM layer and model-backed nodes, prompts, catalogue check with T1, routing data v2, `dev_human` preparation, Kev-0.8B training, calibration, gate and cascade, integration of all tracks, demonstration application, version ladder and error analysis, report and slides | 1, A2.x, A6, Part B, 4, Appendix A |
| Ashmit Ghose (24f1001827) | T4 Ops and Evaluation | Deterministic tool layer and graph adapters, SQL isolation, shared metrics, 40/60 split, evaluation harness, run collation and drift report; `dev_human` labelling | A3, A4, A5, 3 |

## Sign-off

Each member confirms that the sections in their track describe their own work, that every result
cited is backed by committed code, outputs and commands, and that the report is ready for
submission.

| Member | Track | Sign-off |
| --- | --- | --- |
| Shaoni Samanta | T1 | To be confirmed |
| Shivanshu Gupta | T2 | To be confirmed |
| Sathya Prakash | T3 | Signed off, 19 November 2026 |
| Ashmit Ghose | T4 | To be confirmed |
