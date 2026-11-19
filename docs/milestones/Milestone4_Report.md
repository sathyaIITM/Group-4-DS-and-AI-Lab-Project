# Milestone 4: Model Training, Configuration and Evaluation

Project: Analyst Agent for Indian Public Data with Calibrated Decision Models (working title).
Course: DS & AI Lab, GenAI track, Group 4. Date: 19 November 2026. Version 0.2 (draft).

**Status of this file.** Skeleton with the section structure, the requirement map and the
facts already fixed. Sections marked *Pending* are written by the named member once the
corresponding work is merged into `docs/milestone-4`. Every result cites the committed file
that holds it and the command that produced it (Appendix A).

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

## 1. Introduction

### 1.1 Requirement map

The report gives equal weight to the agent system (Part A) and the decision models (Part B).
The TA confirmed that fine-tuning and calibrating the decision models is part of Milestone 4
training. For the agent, training is read as configuring and tuning the system on the
development set, and measuring it end to end.

| Course requirement | Part A: agent system | Part B: decision models |
| --- | --- | --- |
| Training configuration | Section A2; [`configs/agent.yaml`](../../configs/agent.yaml), [`configs/model.yaml`](../../configs/model.yaml), [`configs/inference.yaml`](../../configs/inference.yaml), [`configs/prompts/`](../../configs/prompts/) | Section B1; [`configs/train.yaml`](../../configs/train.yaml) |
| Hyperparameter experiments | Section A4 | Section B2 |
| Generalisation and stability | Section A5 | Section B3 |
| Results and sample outputs | Section A6 | Section B4 |
| Training artifacts | Appendix A | Appendix A; [`models/registry.json`](../../models/registry.json) |
| Key findings | Section 4 | Section 4 |

### 1.2 Response to the Milestone 3 review

*Pending (T3).* Carries forward the items moved to Milestone 4: the human-labelled
`dev_human` set, the fair Kev and Laya comparison, the built agent and its end-to-end
measurement.

### 1.3 Status

*Pending (T3).*

## 2. Data and evaluation sets

### 2.1 Catalogue after the freeze

*Pending (T1).*

### 2.2 End-to-end evaluation set `e2e_v1`

*Pending (T1).*

### 2.3 Human-labelled routing set `dev_human`

*Pending (T3).* Items prepared by T3; labelled independently and by hand by T1, T2 and T4,
two labellers per item and the third adjudicating; Cohen's kappa per decision; share removed
as ambiguous; near-duplicate check against the training data (character 5-gram Jaccard at
least 0.8). Code: [`src/analyst/evaluation/dev_human.py`](../../src/analyst/evaluation/dev_human.py),
[`scripts/label_agreement.py`](../../scripts/label_agreement.py),
[`scripts/check_dev_human_overlap.py`](../../scripts/check_dev_human_overlap.py).

## Part A. The agent system

### A1. Build process

*Pending (T2).*

### A2. Architecture and configuration

*Pending (T2): graph, retrieval nodes, run limits.*

#### A2.x Hosted LLM layer (T3)

**Built.** Client: [`src/analyst/inference/llm.py`](../../src/analyst/inference/llm.py)
(`LlmClient.structured`). Prompt registry:
[`src/analyst/inference/prompts.py`](../../src/analyst/inference/prompts.py); prompts
[`configs/prompts/`](../../configs/prompts/) (`intent`, `sql`, `sql_repair`, `narrate`,
`clarify`, `route`, version 1). Configuration: [`configs/model.yaml`](../../configs/model.yaml).

| Item | Configuration |
| --- | --- |
| Provider and endpoint | Gemini on Vertex AI, OpenAI-compatible Chat Completions, `global` endpoint |
| Default model | `gemini-3.5-flash-lite` (generally available); comparison tier for E2: `gemini-3.8-flash` (generally available; choice to be confirmed by the team) |
| Model selection | Only from `configs/model.yaml` (tier); environment variables supply credentials and the project only |
| Temperature | 0 |
| Prompts | One file per prompt with a header (`id`, `version`, `purpose`, `inputs`, `output_schema`); the SHA-256 of the file is recorded with every call; user text inside `<user_question>`, retrieved content inside `<context>`, delimiter tags removed from values |
| Output validation | Each reply is validated against its Pydantic contract and a rule check (for example, identifiers must be among those retrieved; SQL must be one SELECT on the plan's table; every number in a narration must point to a result cell or a derived value). One retry on a parse, validation or transient error; none on a non-transient provider error |
| Call budget | At most 8 hosted-LLM calls per question, counted before each call |
| Thinking | Set per call purpose as `reasoning_effort`: route, SQL (first attempt), narration and clarification `minimal`; intent and SQL repair `low`; SQL regenerated after a failed result check `medium` |
| Output cap | Per purpose for the visible reply (route 300, intent 512, SQL 1,024, SQL repair 1,024, narration 400, clarification 150 tokens; SQL raised from 512 after a 30-period query was cut off in the smoke test), plus an allowance per thinking level (minimal 0, low 1,024, medium 2,048, high 4,096), because thinking tokens count against the cap |
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
graph tests cover the deterministic tools and SQL runner; end-to-end data validation remains
pending T1.

### A4. Experiments

**Harness built (T4).** [`src/analyst/evaluation/e2e_eval.py`](../../src/analyst/evaluation/e2e_eval.py)
creates the fixed 40/60 action-and-table stratified split, verifies gold SQL read-only, limits
parallel questions to two, retries provider 429 responses through the existing client, scores
the agent-level outcomes, and reports per-case predictions and repeat spread. The shared metric
implementations are in [`src/analyst/evaluation/metrics.py`](../../src/analyst/evaluation/metrics.py).
Split hashes and run targets are recorded in [`configs/evaluation.yaml`](../../configs/evaluation.yaml).
The source set is still marked unvalidated by T1 and the published Parquet tables are not present
in this checkout, so no live runs or score claims are reported yet. Retrieval recall and MRR are
owned by T3.

### A5. Stability

**Framework built (T4).** Three-run scoring reports which case outcomes change across repeats,
with bootstrap intervals per run. Measured spread is pending validated inputs and completed runs.

### A6. Results and error analysis

*Pending measured results (T4, T1, T2).* The harness refuses unvalidated gold and verifies the
gold SQL before spending model credit. T1 validation and the processed observation tables are
prerequisites for reportable results.

## Part B. The decision models

### B1. Training configuration

**Built.** Configuration: [`configs/train.yaml`](../../configs/train.yaml). Run plan:
`python -m analyst.models.kev_runs plan`. Training notebook:
[`notebooks/kev_train_t4.ipynb`](../../notebooks/kev_train_t4.ipynb).

| Item | Value |
| --- | --- |
| Decision | Domain (phase 1); tool selection stays on Jev until phase 2 |
| Base model | `Qwen/Qwen3.5-0.8B-Base`, revision `dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68` |
| Warm start | `--init_from jaredpalmer/kev-0.8b`, revision `bf75a6a8848ea6960ff2ed108d9ed44c2941174f` (LoRA rank 16, pointer head 256) |
| Training code | Kev, commit `2074cc44256200bb37540103fa4572901faa10f3` |
| Adapter | LoRA rank 16 on all modules (rank fixed by the warm start) |
| Optimiser and schedule | AdamW; OneCycle schedule with 10% warm-up; global gradient-norm clipping at 1.0 (constants of `kev.train`) |
| Base configuration B0 | Learning rate 2e-5, 2 epochs, batch 1, gradient accumulation 8, seed 0 |
| Precision | fp32 weights and compute. `kev.train` offers fp32 or bf16 only, and the T4 has no bf16 |
| Hardware | Colab and Kaggle T4 (16 GB) |
| Data | `train.v2`, `calibration.v2`, `dev_synthetic.v2`; hashes in [`data/MANIFEST.md`](../../data/MANIFEST.md) (*Pending*, routing data v2) |
| Calibration | One temperature fitted on the calibration split by NLL; applied unchanged to dev |

Constraint found while preparing the sweep: under `--init_from`, `kev.train` requires the LoRA
rank, head dimension and base revision to equal those of the released checkpoint
(`kev/checkpoint.py`, `COMPAT_FIELDS`). The LoRA-rank runs (8, 16, 32) therefore start from the
base model and are compared with each other, not with B0.

### B2. Hyperparameter experiments

*Pending (T3).* One factor at a time from B0: learning rate (1e-5, 2e-5, 4e-5), epochs (1, 2,
3), training-set size (250, 500, 1,000, full), seeds (0, 1, 2); LoRA rank from the base model.

### B3. Generalisation and stability

*Pending (T3).* Warm start against the base model; held-out-table split; clipped steps per
epoch; seed spread; temperature scaling; option-order flip rate; early stop by epoch count on
calibration NLL.

### B4. Results

*Pending (T3).* Per decision on `dev_human`: Kev zero-shot and fine-tuned, Jev, Laya zero-shot
and fine-tuned, v0 LLM; accuracy with a bootstrap 95% interval, macro-F1, per-label F1, NLL,
Brier, ECE before and after temperature scaling, AUROC of correctness, reliability diagrams,
latency and cost per 1,000 decisions; the Kev-to-Jev cascade; the gate outcome, reported
either way. Code: [`src/analyst/evaluation/decision_eval.py`](../../src/analyst/evaluation/decision_eval.py).

## 3. Drift baseline and log collation

**Built (T4).** Run bundles use a versioned manifest with row counts and file hashes;
[`src/analyst/ops/collate_runs.py`](../../src/analyst/ops/collate_runs.py) validates bundles,
deduplicates imports and records conflicting rows without overwriting them. The offline drift
report in [`src/analyst/ops/drift.py`](../../src/analyst/ops/drift.py) compares outcome, routing,
confidence, result-check, repair, cost and latency signals, with minimum window sizes and human
review suggestions. No real baseline or simulated-shift report is claimed because the evaluation
runs and collated warehouse are not yet available.

## 4. Key findings

*Pending (all).*

## Appendix A. Artifacts and reproduction

*Pending (T3 with all).*

## Contribution log

*Pending.* [`WORKLOG.md`](../../WORKLOG.md) holds the weekly record of individual contributions.
