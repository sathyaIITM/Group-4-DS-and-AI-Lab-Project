# Milestone 5: Evaluation and Analysis of Results

Project: Analyst Agent for Indian Public Data with Calibrated Decision Models (working title).
Course: DS & AI Lab, GenAI track, Group 4. Date: 26 November 2026. Version 0.1 (skeleton).

**Status of this file.** Skeleton: the sixteen sections of the evaluation outline, the owner of
each, the content it must hold and the files it will cite. Facts already fixed (plan, sets,
configurations, training of the selected model) are written; every result is marked
*Pending* until its run is committed. Every result cites the committed file that holds it and
the command that produced it (Appendix F).

**Scope of the evidence.** As in Milestones 3 and 4, every statement is tagged:

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
| 0.1 | 25 Nov 2026 | Skeleton: sixteen sections, owners, response map to the Milestone 4 review, evaluation sets and configurations |

---

## 1. Introduction

*Owner: T3.*

### 1.1 Project objective

A non-expert (primary users: journalists and fact-checkers) gets a correct, explained and
verifiable answer from Indian public data in about 30 seconds. A hosted LLM writes queries,
plans and narration; calibrated decision models make the control decisions; deterministic
checks verify every figure against the data.

### 1.2 Scope of the evaluation

Two parts, as in Milestone 4:

- **Part A, the complete agent:** end-to-end success, execution accuracy, interpretation,
  completeness, abstention and clarification, latency and cost, for versions v2, v3 and v4.
- **Part B, the decision models:** the domain decision (Kev-0.8B `ep3`, Jev, Laya) and the
  tool-selection decision (phase 2: joint Kev model), on human-labelled sets, with calibration
  and the cascade, including hard and unfamiliar questions.

### 1.3 Systems evaluated

| System | What it is | Section |
| --- | --- | --- |
| v2 (Milestone 4 baseline) | Hosted LLM (`gemini-3.5-flash-lite`), guidance cards and verified examples, Jev routing; frozen commit `a2c8c7d` | 6, 7 |
| v2 (Milestone 5) | v2 with the Milestone 5 fixes to place, period, clarification and follow-up handling | 6, 7, 9 |
| v3 | v2 (Milestone 5) with the intent prompt optimised by GEPA on development items | 6, 7, 8, 9 |
| v4 | v3 with fine-tuned Kev-0.8B on the domain decision and the cascade to Jev; tool selection on Kev only if the phase 2 gate passes | 6, 7, 9 |
| Kev-0.8B `ep3` | Domain decision, selected in Milestone 4 | 3, Part B |
| Kev-0.8B joint (phase 2) | Tool selection and domain in one model | 3, 8, Part B |
| Jev | Hosted decision model (zero-shot) | Part B |
| Laya | Comparator, fine-tuned with the library defaults | Part B |

### 1.4 Objectives of Milestone 5 and response to the Milestone 4 review

| # | Review point | Response | Where | Status |
| --- | --- | --- | --- | --- |
| 1 | End-to-end success flat; failures before SQL | General fixes on development items only; paired comparison on the frozen test set | 6, 7, 9, 10 | Pending |
| 2 | Clarification 0.278, abstention precision 0.55-0.57; disputed gold | Expected-action rules v2; validation of every development and test item; Milestone 4 runs re-scored on validated gold; clarification slot scored | 4, 6, 10 | Pending |
| 3 | Test set too small; scoring too lenient | 40 new blind test items (100 in all); scorer v3 checks interpretation, completeness, unit, period and evidence; blind human rating | 4, 5, 6 | Pending |
| 4 | Kev not evaluated inside the agent | v4 against v3 and v2 on the same frozen test set | 6, 7 | Pending |
| 5 | Limits of the decision-model evaluation | Laya fine-tuned; phase 2 joint model gated on re-adjudicated tool labels (guide 1.1); limits kept in the conclusions | Part B, 13 | Pending |
| 6 | Calibration and cascade on hard cases and inside the agent | `stress_v1` (80 items); Kev confidence logged in agent runs | 6, 11 | Pending |

---

## 2. Experimental setup

*Owners: T1 (data), T3 (environment).*

### 2.1 Hardware and software environment

| Component | Environment |
| --- | --- |
| Agent runs and scoring | Local machine: Apple M5, 16 GB, macOS; Python 3.13.14; packages in [`requirements.lock.txt`](../../requirements.lock.txt) |
| Kev training | Kaggle, 2 x Tesla T4 (CUDA, fp32); Kev at commit `2074cc44` with its own lock file |
| Laya training | Colab, Tesla T4 (CUDA); `laya` 0.4.23 |
| Hosted LLM | Vertex AI, `gemini-3.5-flash-lite` (default tier), global endpoint, temperature 0; the large tier for GEPA's reflection only |
| Decision-model serving | Kev served locally (`scripts/serve_kev.sh`, MPS, fp32); Jev hosted |

### 2.2 Frameworks and libraries

LangGraph (agent graph), DuckDB (read-only SQL over versioned Parquet), sqlglot (SQL checks),
Pydantic (contracts), BM25 and `BAAI/bge-small-en-v1.5` (retrieval), Kev (`kev.train`,
`kev.serve`), DSPy 3.5.0 and `gepa` 0.1.4 (prompt optimisation), scipy (paired tests).

### 2.3 Dataset versions

*Pending (T1):* catalogue of 14 tables with hashes from [`data/MANIFEST.md`](../../data/MANIFEST.md);
reference files added for place resolution.

### 2.4 Evaluation sets and splits

| Set | File | Items | Use |
| --- | --- | --- | --- |
| `e2e_test` v1 (continuity) | [`data/eval/e2e_test.v1.jsonl`](../../data/eval/e2e_test.v1.jsonl) | 60 | Test, comparable with Milestone 4 |
| New test items (blind) | `data/eval/e2e_test_ext.v1.jsonl` | 40 | Test; written by T1, unseen by the developers before the code freeze |
| `e2e_dev` v1 and extra | [`data/eval/e2e_dev.v1.jsonl`](../../data/eval/e2e_dev.v1.jsonl), [`e2e_dev_extra.v1.jsonl`](../../data/eval/e2e_dev_extra.v1.jsonl) | 60 | Development, GEPA training and validation |
| Development supplement | [`data/eval/e2e_dev_m5.v1.jsonl`](../../data/eval/e2e_dev_m5.v1.jsonl) | 30 | Development |
| `dev_human` v1 / v1.1 | [`data/labels/dev_human_v1/`](../../data/labels/dev_human_v1/) | 198 | Decision-model test; tool labels re-adjudicated under guide 1.1 (v1.1) |
| `stress_v1` | [`data/labels/stress_v1/`](../../data/labels/stress_v1/) | 80 | Hard and unfamiliar cases for the domain decision |
| Routing data v2 | [`data/splits/kev/`](../../data/splits/kev/) | 1,876 / 322 / 355 | Training, calibration, model selection |

### 2.5 Random seeds and reproducibility

Kev runs: seeds 0 and 1 for the joint model, seeds 0-2 for B0 (Milestone 4). Data split and
GEPA split: seed 0. Bootstrap: 10,000 resamples, seed 0. The test runs use the frozen commit
*(pending)*; commands in Appendix F.

### 2.6 Evaluation workflow

*Pending (T3):* validation of the gold against the expected-action rules; code freeze; three
runs per configuration on the frozen test set; scoring with scorers v2 and v3; paired
comparisons; blind human rating; decision-model scoring on `dev_human` and `stress_v1`.

---

## 3. Model training summary

*Owner: T3.*

### 3.1 Domain decision: Kev-0.8B `ep3` (selected in Milestone 4)

| Item | Value |
| --- | --- |
| Architecture | `Qwen/Qwen3.5-0.8B-Base` with a rank-16 LoRA (all targets) and Kev's pointer head; warm start `jaredpalmer/kev-0.8b@bf75a6a8` |
| Optimiser and schedule | AdamW (weight decay 0.01), OneCycle with 10% warm-up, gradient clipping at norm 1.0 |
| Learning rate, batch, epochs | 2e-5; batch 1 x accumulation 8; 3 epochs |
| Loss | Cross-entropy over the options |
| Early stopping | None (`kev.train` saves per epoch only for full-weight runs); training horizons compared as separate runs |
| Checkpoint selection | Temperature fitted on calibration; lowest `dev_synthetic` NLL after temperature, beyond the B0 seed spread |
| Calibration | One temperature, 3.763, fitted by NLL on the calibration split |
| Training duration | *Pending: from the run record* |

### 3.2 Phase 2: joint model for tool selection and domain

Same recipe as `ep3`, on routing data v2 with one single-question record per decision (3,752
records), seeds 0 and 1; one temperature per decision. Selection fixed in advance in
[`configs/train.yaml`](../../configs/train.yaml). *Pending: training records and selection.*

### 3.3 Laya comparator

*Pending: library defaults (4 epochs, micro-batch 8 x accumulation 8), 15.8 minutes on a Colab
T4; scores.*

### 3.4 Prompt optimisation for v3 (GEPA)

*Pending: component optimised (intent instructions), development items, budget, candidates and
validation scores ([`outputs/reports/gepa_v3.json`]).*

---

## 4. Evaluation methodology

*Owners: T1 (4.1-4.3), T3 (4.4-4.6).*

### 4.1 Test sets

*Pending (T1).*

### 4.2 Ground-truth preparation

*Pending (T1):* how the items were written; gold values from executing the gold SQL.

### 4.3 Ground-truth validation

*Pending (T1):* the expected-action rules v2 ([`data/eval/README.md`](../../data/eval/README.md));
validators per set; number of items changed per set and per rule; disputed items.

### 4.4 Evaluation protocol

*Pending (T3):* three runs per configuration; frozen commit; the 60 continuity items and the
40 blind items reported separately and together.

### 4.5 Baselines

v2 at the Milestone 4 commit for the agent; zero-shot Kev and Jev for the decision models.

### 4.6 Success criteria

Objectives O1-O8 of the project plan and the gate fixed in [`configs/inference.yaml`](../../configs/inference.yaml)
(within 3 points of Jev, ECE at most 0.10 after calibration). *Pending: table of targets.*

---

## 5. Performance metrics

*Owner: T3.*

### 5.1 Agent metrics (Part A)

| Metric | Definition | Why |
| --- | --- | --- |
| End-to-end success (scorers v2, v3) | Share of items whose outcome meets every applicable check | The user-facing measure |
| Execution accuracy | Agent result equals the gold result (projected) | Query correctness alone |
| Interpretation, completeness, unit, period, evidence | Scorer v3 checks ([`scorer_v3.py`](../../src/analyst/evaluation/scorer_v3.py)) | Requested by the review: correct reading of the question and complete, traceable answers |
| Abstention precision and recall | Over non-answers (decline, clarify) | Reliability of refusals |
| Clarification slot accuracy | The agent asks for the missing slot | Review point 2 |
| Wrong-answer rate | Released answers that fail | Harm of a wrong figure |
| Latency, calls, tokens, cost per answer | From the run log | Objectives O5, O6 |
| Human rating | Interpretation, completeness, wording (0-2), two raters, kappa | What code cannot judge |

### 5.2 Decision-model metrics (Part B)

Accuracy with a bootstrap interval, macro-F1 and per-label F1, NLL, Brier score, ECE (10 bins)
before and after temperature, AUROC; for the cascade, the share handled by Kev at a 5% error
budget and the escalation rate.

---

## 6. Experimental results

*Owners: T3 (Part A and Part B).*

### 6.1 Part A: complete agent

*Pending:* table per configuration (scorers v2 and v3), per-check rates, comparison with the
targets; Milestone 4 runs re-scored on validated gold.

### 6.2 Part B: decision models

*Pending:* domain on `dev_human` and `stress_v1`; tool on `dev_human` v1.1; reliability
diagrams; ROC and PR curves; Kev confidence inside the agent.

---

## 7. Baseline comparison

*Owner: T3.*

*Pending:* paired differences v2 (M4) to v2 (M5), v2 (M5) to v3, v3 to v4, with bootstrap
intervals and McNemar tests; decision models against zero-shot Kev, Jev and Laya.

---

## 8. Hyperparameter analysis

*Owner: T3.*

*Pending:* Kev runs of Milestone 4 (learning rate, epochs, seeds, from-base rank) and the phase
2 seeds; temperature; cascade threshold; GEPA budget.

---

## 9. Ablation study

*Owner: T2 (from the tables of Section 6).*

*Pending:* the version ladder read as an ablation (without guidance cards, without verified
examples, without the Milestone 5 fixes, without the optimised prompt, without Kev); retrieval
without place and indicator slots; Kev without temperature; v4 without the cascade.

---

## 10. Error analysis

*Owners: T2 (Part A), T3 (Part B).*

*Pending:* failure classes with representative cases, false positives and false negatives,
agent errors separated from gold corrections; Kev confusion matrices and misclassified items.

---

## 11. Model robustness

*Owners: T2 (agent), T3 (decision models).*

*Pending:* paraphrase, Hindi and Hinglish, typos, follow-ups and edge cases for the agent;
`stress_v1` for the domain decision; the held-out-table result if run.

---

## 12. Computational performance

*Owners: T2 (agent), T3 (decision models).*

*Pending:* agent latency (first event, p50, p95), calls, tokens and cost per answer; Kev and
Laya training time, inference latency, memory and model size.

---

## 13. Limitations

*Owners: all; edited by T3.*

*Pending:* dataset, agent, evaluation and model limitations; ethical considerations.

## 14. Possible improvements

*Owner: T3.* *Pending.*

## 15. Discussion

*Owner: T3.* *Pending.*

## 16. Conclusion

*Owner: T3.* *Pending.*

---

## Appendices

- A. Complete metric tables. *Pending.*
- B. Confusion matrices, ROC and PR curves, reliability diagrams. *Pending.*
- C. Learning and loss curves; hyperparameter search results. *Pending.*
- D. Sample predictions and failure cases. *Pending.*
- E. Model and agent configuration ([`configs/`](../../configs/)).
- F. Artifacts, evaluation scripts and reproduction commands. *Pending.*

## Contribution log

Milestone 5 work per member; the weekly record is in [`WORKLOG.md`](../../WORKLOG.md), and the
commits are on `docs/milestone-5`.

| Member | Track | Milestone 5 contribution | Report sections |
| --- | --- | --- | --- |
| Shaoni Samanta (21f1003157) | T1 Data and Tools | *To be completed* | 2, 4.1-4.3, 13 |
| Shivanshu Gupta (22f3002985) | T2 Agent | *To be completed* | 9, 10, 11, 12, 13 |
| Sathya Prakash (21f1006001) | T3 Model | *To be completed* | 1-8, 10-16 |
| Ashmit Ghose (24f1001827) | T4 Ops and Evaluation | *To be completed* | *To be completed* |

## Sign-off

Each member confirms that the sections in their track describe their own work, that every result
cited is backed by committed code, outputs and commands, and that the report is ready for
submission.

| Member | Track | Sign-off |
| --- | --- | --- |
| Shaoni Samanta | T1 | To be confirmed |
| Shivanshu Gupta | T2 | To be confirmed |
| Sathya Prakash | T3 | To be confirmed |
| Ashmit Ghose | T4 | To be confirmed |
