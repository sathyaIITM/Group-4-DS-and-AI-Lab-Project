# Analyst Agent for Indian Public Data with Calibrated Decision Models

Oct 22, 2026

**Milestone 1: Problem Definition & Literature Review**

**Project focus.** A trustworthy natural-language interface to a curated set of Indian public statistics, designed to show its evidence, communicate calibrated confidence, and decline when the available data cannot support an answer.

DS & AI Lab Project · Generative AI

*Milestone 1 establishes the problem, research grounding, scope, contribution, and the evidence required to test the proposed approach. It does not claim that the system has already achieved its targets.*

---

## 1. Executive Summary

This project builds an analyst agent that gives a non-expert a correct, explained and verifiable answer to a question about Indian public data within about 30 seconds, states how far the answer can be trusted, and declines when the catalogue cannot answer. Decision models, not LLM calls, make the agent's control decisions and verify results; an LLM is used only where text must be generated.

| Item | Summary |
| --- | --- |
| Problem | Even within a curated set of Indian public tables, formats, units, periods and survey definitions are inconsistent, and general-purpose assistants return figures a non-expert cannot verify. Discovery across portals is handled by an admin-operated onboarding path, not by the agent. |
| Primary users | Journalists and fact-checkers. Students and researchers, NGO staff and local administrators are secondary users; a data-steward/admin team operates the catalogue. |
| Approach | A fixed LangGraph workflow. A fine-tuned open decision model (Kev) makes tool-selection and domain decisions in batched calls; a hosted LLM writes queries, plans and narration; a hosted decision model (Jev) takes every other decision, including coverage, and verifies each result, calibrated on our labels. Queries run read-only in DuckDB over versioned Parquet, and an evidence panel shows what was executed. |
| Primary contribution | Calibrated trust in a new deployment context: Indian data conventions as tested components, decision models as the control layer (fewer LLM calls, lower cost and latency), calibrated verification, and decline-and-log for missing data. |
| Evidence | One frozen 200-question test set across versions v0 to v6: claim support at least 0.95, ECE at most 0.10, abstention precision at least 0.85, p95 latency at most 20 s; accuracy differences are reported with confidence intervals, and each mechanism's contribution is isolated by ablation. |
| Constraints | Free Colab T4 for Kev fine-tuning; one Compute Engine VM; hosted APIs; about US$65–170 (team estimate) against a US$300 Google Cloud credit. |

## 2. Problem Definition

A person who needs a specific figure from Indian public data faces four barriers between the question and a trustworthy answer. This project addresses the last three. The first is assumed away by a curated catalogue, and that boundary is stated here deliberately rather than left implicit.

- **Discovery** *(not addressed by the agent)*. The same indicator sits across data.gov.in, MoSPI, RBI, IMD, agriculture, NFHS and Census releases, and table titles often do not state their contents. This project works over an admin-curated catalogue of 8–12 tables, so cross-portal discovery is out of scope for the question-answering claim and is deferred to the onboarding pipeline (section 4). The remaining three barriers survive curation and are what the agent must solve.
- **Format.** Years as columns, footnote and total rows, mixed units (lakh, crore, per cent) and changing place names (Orissa and Odisha, Bangalore and Bengaluru, Andhra Pradesh before and after Telangana in 2014).
- **Domain conventions.** Usual versus current weekly labour status; a July–June agricultural year against an April–March government finance year; survey rounds that are not always comparable.
- **Trust.** A general-purpose assistant gives a figure without its table, filter, year or reliability, so a non-expert cannot verify it.

Example: "Compare female labour force participation in Tamil Nadu and Bihar since 2018. Is the gap closing?" needs the right PLFS tables, one worker-status definition and age group, consistent state names and survey years, and the gap computed per year with its trend. An analyst does this by hand; the intended user cannot.

**Problem statement.** Build an agent that gives a non-expert a correct, explained and verifiable answer to a question answerable from a curated catalogue of selected Indian public tables, in plain language and within about 30 seconds (measured as a p95 end-to-end latency of at most 20 s, O5), and that states how far each answer can be trusted: it reports a calibrated confidence, and it declines, naming the missing coverage, when the catalogue cannot answer the question. Finding and onboarding new tables is a separate, admin-operated path and is not part of the question-answering claim.

## 3. Relevance and Stakeholders

Open data creates public value only when intended users can use it, and an unsupported figure in a news story, thesis or programme plan does more harm than an answer that is withheld. The need is sharpest in newsrooms and fact-checking desks (citable comparisons on deadline, quoted figures checked against official data), education and research, NGOs and local administration (district indicators without SQL skills) and public accountability.

| Stakeholder | Need | Value provided |
| --- | --- | --- |
| Journalists and fact-checkers (primary) | Fast, citable state and year comparisons; a quoted figure checked against official data | Source links, data version, visible checks, stated confidence |
| Students and researchers (secondary) | Trends and plain definitions, e.g. "usual status" | Correct analysis without knowing each survey's conventions |
| NGO staff and local administrators (secondary) | District-level indicators for planning | Self-service answers without SQL or cleaning |
| Admin team (operator) | Control over which data and model changes reach users | Approval portal, review queue, ranked list of unmet data requests |
| Data publishers (secondary) | Which data users seek and cannot find | Data-request log exposes catalogue gaps |
| Citizens, policymakers and the course team (secondary) | Decisions based on correct figures; evidence the system works | Fewer unsupported claims; frozen tests, versioned results, stated limits |

## 4. Scope and Boundaries

The initial catalogue has 8–12 core tables across labour, agriculture, rainfall, prices and economy, and health. The specific tables are not named at this milestone: candidates are profiled and the list is frozen in Milestone 2, after which the catalogue is fixed for the remainder of the project. Further tables enter only through a validated, admin-approved onboarding pipeline. The core is finished before optional items begin.

| Tier | In scope | Target |
| --- | --- | --- |
| Core | Fixed LangGraph workflow; hosted-LLM query generation; decision layer (Kev for tool selection and domain behind gates; Jev for coverage, verification and any decision Kev does not pass); catalogue and domain guidance; retrieval over verified examples, guidance cards and column descriptions using a general open embedding model with an optional reranker; core tools (place, time and unit resolvers, query runner, statistics, chart); read-only execution; result checks and evidence panel; data-gap detection and request log; chart selection; streaming UI; follow-up memory; evaluation suite; Docker Compose deployment with tracing | 26 Nov |
| Should | Admin portal (dataset onboarding, data requests, review queue); drift detection; iteration dashboard; human-approved retraining procedure | 10 Dec |
| Stretch | Kev for clarification and intent; fine-tuned retrieval model (the E7 design is retained in the repository); one further Kev decision (coverage is the candidate); Kev-4B comparison; fine-tuning Kev for answer verification; user-profile memory; India maps; PDF export; e-mail alert on repeated data requests; data.gov.in API search | If time permits |

**Out of scope:** training a query-writing model (a hosted LLM writes queries); free-form code execution by the agent; table extraction from PDFs; forecasting policy outcomes; legal advice; real-time feeds (the catalogue is versioned and static between onboardings); answers from datasets an admin has not verified and published; cross-portal dataset discovery by the agent; voice input and non-English answers.

**Cut order.** Under schedule pressure, items are cut in this order, each first reduced to a minimal version: (1) Stretch items, beginning with PDF export, India maps and the e-mail alert, and ending with the additional Kev decisions; (2) iteration dashboard, to a generated table of per-version results; (3) drift detection, to an offline script flagging a rise in low-coverage or low-confidence questions against a fixed threshold; (4) human-approved retraining procedure, to a documented manual run with recorded admin approval; (5) admin portal, to one review page for onboarding and data requests. E6 runs only if items 3 and 4 survive. Core items are not cut.

## 5. Literature Review: Current Approaches

Relevant research falls into seven lines: decision models, routing and cascades, calibration, verification, abstention, grounded data analysis with query-generation benchmarks, and prompt optimisation. No reviewed system combines them for Indian public data with calibrated confidence and an evidence panel a non-expert can read. Bracketed numbers refer to section 12.

### 5.1 Decision models and open alternatives

A decision model reads a state and typed questions (yes/no, one of N, ordered score) and returns probabilities in one forward pass instead of generated text \[5\]\[6\]. TypeSafe AI's Jev is the hosted reference (vendor-reported 40 to 200 times faster than frontier LLMs; early access) \[5\]. Open alternatives from 2026 are Kev (Qwen3.5 with a LoRA adapter and pointer head, 0.8B to 27B parameters) \[7\]\[8\], Laya (ModernBERT, 322M and 421M) \[9\], CLM-v0.1-8B \[10\] and RubriX-8B \[11\].

Their intended use is routing, classification and policy checks. Kev's model card reports that Kev-0.8B scored below chance on the When2Call tool-routing benchmark, is weak on knowledge-heavy questions (0.230 against Jev's 0.840 on MMLU-Pro) and scores 0.586 against 0.757 for Jev on its own breadth benchmark \[8\]; Laya's base checkpoints score near chance zero-shot (0.362) \[9\]. Kev-4B reports 0.817 (development) and 0.838 (test) accuracy on new sources against 0.857 for Jev on development sets only, and Kev-9B's calibration error falls from 0.103 to 0.041 after temperature scaling \[7\]. Fine-tuning narrows the gap: Laya rises from 0.362 to 0.766 \[9\], and Kev reports 0.83 from a released checkpoint against 0.33 from the base model in one user's test \[7\]. All figures are self-reported, and this review found no independent check of their calibration.

Open decision models therefore suit closed-set routing after fine-tuning and calibration on the target task, while knowledge-heavy judgements stay with a larger model. This project adopts that division: Kev for tool selection and domain in the core system, with clarification and intent as stretch additions; Jev for coverage, verification and every other decision. Tool selection is knowingly the riskiest of these choices, because the Kev-0.8B card reports below-chance zero-shot accuracy on exactly this kind of routing \[8\]. It is kept in the core for that reason — it is where the fine-tuning claim is most informative — and domain, a closed-set classification of the kind the same literature says these models suit, is the safer second core decision. The week-1 routing test and the E3 gate decide whether tool selection stays on Kev or reverts to Jev, and the outcome is reported either way.

### 5.2 Routing, tool selection and cascades

Agents commonly pick their next action with an LLM call that interleaves reasoning and acting \[32\]; each call adds latency and cost, and tool-calling decisions remain error-prone \[31\]. Cascades and routers reserve expensive models for hard queries: FrugalGPT reports matching the best single LLM with up to 98% lower cost \[29\], and RouteLLM cuts cost by more than 2 times in some cases without reducing quality \[30\]. This project applies the principle to agent decisions: a small fine-tuned model decides first, and a hosted decision model takes uncertain calls. Gains are measured on this task, not assumed.

### 5.3 Calibration, verification and abstention

Modern neural networks are often poorly calibrated, and temperature scaling is a simple correction \[1\]; language models can also estimate whether their own answer is correct \[2\]. Kev applies one fitted temperature per checkpoint, which does not change which answer ranks first \[7\], so an escalation threshold is meaningful only if calibration is checked on the target data.

Trained verifiers improve results on math word problems \[12\], and step-level supervision beats final-answer supervision on MATH \[13\]; this review found no learned verifier applied to analytic answers over public statistics. LLM judges agree with humans over 80% of the time but show position, verbosity and self-enhancement bias \[3\], and panels of smaller models can beat one large judge at lower cost \[4\]. Because verification draws on world knowledge, where open models trail Jev \[8\], this project verifies with a hosted decision model and treats a fine-tuned Kev verifier as an extension.

Selective classification trades coverage for lower risk \[14\], and a survey organises abstention in LLMs by query, model and human values \[15\]. This review found no benchmark for declining because the requested data is absent from a catalogue.

### 5.4 Grounded data analysis, query generation and prompt optimisation

DataGemma is the closest precedent: it grounds an LLM in Data Commons statistics by emitting data queries (RIG) or placing retrieved tables in the prompt (RAG) \[16\]. It is not India-specific, shows no executed query and reports no calibrated confidence. DA-Code (best result 30.5% on 500 tasks) \[17\] and InfiAgent-DABench \[18\] score code-written analyses against reference answers, not whether a non-expert can trust them. DSPy compiles LLM pipelines to maximise a metric \[19\]; GEPA evolves prompts by reflection \[20\]. Here prompt optimisation is run manually on generation steps and decision-model instructions.

Text-to-SQL benchmarks give the nearest evidence on query generation. Spider (10,181 questions, 200 databases) \[33\] and BIRD (12,751 question–SQL pairs, 95 databases) \[34\] are the standard benchmarks; at publication the best model tested reached 40.08% execution accuracy on BIRD against 92.96% for humans \[34\], and BIRD test accuracy has since reached 55.9% (DIN-SQL) \[35\] and 71.10% in a high-compute setting (CHESS, preprint) \[36\]. Execution accuracy is therefore the standard measure, and query generation is advancing quickly, which is why this project buys query writing from a hosted LLM and does not train it. The benchmarks use curated single databases, report no calibrated confidence and include no question the catalogue cannot answer, so their figures do not transfer to Indian survey tables.

### 5.5 Commercial and public tools

Current tools address access, or natural-language analytics for teams that curate their own data. None checks Indian survey conventions, shows its evidence to a non-expert and reports a calibrated confidence.

| Category and example | Function | Limitation for the intended users |
| --- | --- | --- |
| General chat assistants with code execution | Write code over an uploaded file or a question; return text and charts | No catalogue of Indian datasets, so the user must find and clean the file; definitions such as usual versus weekly status apply only if specified; hard to verify; no confidence reported |
| Warehouse and BI copilots: Snowflake Cortex Analyst \[21\], Databricks Genie \[22\] | Natural-language questions over governed organisational tables; Snowflake reports 90%+ accuracy on an internal benchmark, attributed to a data-team-written semantic model | Need a curated warehouse and a semantic-layer author; accuracy is vendor-reported on private benchmarks; no Indian geography codes, fiscal-versus-agricultural years or comparability rules |
| Hosted decision API: Jev \[5\] | Typed probabilities for routing, verification and scoring | General-purpose; not calibrated on analytic answers or catalogue coverage; early access; vendor-reported speed |
| MoSPI eSankhyiki MCP server \[23\]\[24\] | Beta from 6 February 2026 with 7 products (including PLFS, CPI, WPI), 21 by 23 March 2026; lets an AI tool query official statistics | An access layer: no unit or comparability checks, definitions or confidence; MoSPI only. A data source here, not a competitor |
| Open data portal: data.gov.in \[25\] | Catalogue and APIs for ministry and state datasets (357,955 resources, 12,531 catalogues; 22 October 2026) | Catalogue search and download; no check of units, periods or comparability |

## 6. Metrics Used in Existing Work

Existing work defines success mainly as accuracy against reference answers. Calibration, selective accuracy, the cost of control decisions and latency are reported separately or not at all.

| Metric family | Used by | What it measures | Limitation for this project |
| --- | --- | --- | --- |
| Task accuracy against reference answers | Spider \[33\], BIRD \[34\], DA-Code \[17\], InfiAgent-DABench \[18\], DataGemma \[16\] | Whether the executed query or analysis matches a reference | Curated databases or code-written analysis; not trust or readability for a non-expert; no confidence |
| Tool-calling and decision quality: accuracy, F1, AUROC, Brier score, ECE, share of decisions a small model can take within a fixed error budget (5% here, section 9) | When2Call \[31\], Kev \[7\], Laya \[9\] | Whether to call a tool, ask or decline; quality of typed probabilities | Generic tools and tasks; not agent control or catalogue coverage |
| Cost and quality of routing | FrugalGPT \[29\], RouteLLM \[30\] | Cost reduction at matched quality | Measured on LLM answers, not control decisions |
| Selective prediction and abstention | \[14\], \[15\] | Quality of the answers given when declining is allowed | Not applied to absence from a catalogue |
| Verifiers and judges | \[12\], \[13\]; \[3\], \[4\] | Gain from learned verifiers; judge agreement with humans (over 80%) | Reasoning tasks; judge biases; no end-user calibration |
| Calibration: ECE, reliability plots | \[1\], \[2\] | Whether confidence matches accuracy | Seldom shown to end users of analytic assistants |
| Latency and cost | Vendor claims \[5\] | Whether accuracy is affordable | Rarely reported beside accuracy; unverified |

Objectives O1 to O8 (section 9) cover these families on one frozen test set and add claim-support rate, chart appropriateness and LLM calls per answer, which the sources above do not report. Execution accuracy, the primary answer metric, is standard in the text-to-SQL benchmarks \[33\]\[34\].

## 7. Gaps and Research Opportunity

Six gaps separate current tools from a non-expert obtaining a trustworthy answer from Indian public data. Each can be built and measured.

| Gap | Evidence | Opportunity | How it will be tested |
| --- | --- | --- | --- |
| 1. Indian data conventions (renamed geographies, fiscal versus agricultural years, lakh and crore, survey comparability) are left to the user | Benchmarks use generic data \[17\]\[18\]\[33\]\[34\]; DataGemma is global \[16\]; the MoSPI server is an access layer \[23\]\[24\] | Place, time and unit resolvers; per-domain guidance cards | Component tests; accuracy by domain |
| 2. Declining when data is missing from the catalogue is not studied | No catalogue-coverage benchmark found; abstention work targets general model abstention \[15\] and selective classification \[14\] | Coverage decision (Jev, calibrated); decline with reason; logged data request | At least 20 unanswerable questions; abstention precision and recall |
| 3. Answers are verified for analysts, not non-experts | Vendor tools show queries but need a data team \[21\]\[22\] | Evidence panel (query description, executed query, sources, data version, agreement of independent queries, match with an official report) | Claim-support rate; human-rated clarity |
| 4. Control decisions are LLM calls, adding latency and cost | One LLM call per step \[32\]; routing cuts cost \[29\]\[30\]; tool decisions error-prone \[31\] | Batched small decision model for tool selection and domain; uncertain calls escalate to Jev | LLM calls per answer, latency, cost |
| 5. Accuracy is reported alone | Vendor-reported speed \[5\]; no independent calibration check of open models found | Every version reports accuracy, cost, latency and calibration | Frozen-set comparisons; version ladder |
| 6. Open decision models are untested for control and coverage; learned verification is studied on reasoning only | Zero-shot Kev-0.8B trails Jev (0.586 against 0.757) and is below chance on tool routing \[8\]; verifier work on math \[12\]\[13\] | Fine-tune and calibrate Kev per decision behind a gate against Jev; verify with a calibrated hosted model | Per-decision accuracy and ECE; share handled within the 5% error budget |

## 8. Contribution and Differentiation

The contribution is calibrated trust in a new deployment context, not a new architecture or query-generation algorithm.

- **New deployment context (primary).** Place resolution to government codes, fiscal and agricultural year parsing, unit normalisation, per-domain guidance cards, retrieval over guidance cards and column descriptions, and guided onboarding.
- **Decision models as the control layer.** Kev handles tool selection and domain in batched calls when it passes its gate; uncertain calls and all other decisions, including coverage, go to Jev. Clarification and intent are stretch extensions of the same mechanism.
- **Calibrated verification.** Jev verifies each result and claim; the confidence badge is calibrated on labelled examples.
- **Safe failure and usability.** Decline and log when coverage is missing; an evidence panel shows the executed query, sources, data version and agreement of independent queries, with one matched chart.
- **Efficiency and measurable iteration.** LLM calls only for generation, batched decisions and caching; a version ladder with ablations shows where each gain comes from.

**Limits of the claim.** No state-of-the-art claim, new learning algorithm, or generalisation beyond the chosen domains and catalogue. Cross-portal dataset discovery is explicitly not claimed. Query writing uses a hosted LLM, expected to beat a model trained on free compute at a small per-question cost and without GPU serving. Kev handles a decision only if it passes its gate, but its fine-tune is always run and reported; otherwise Jev decides. Verification depends on Jev; access is held through TypeSafe AI directly and through OpenRouter, and if both lapse a calibrated LLM judge replaces it on the same labels. A fine-tuned Kev verifier is an extension if time, budget and routing gates allow.

## 9. Evidence Plan and Success Criteria

The approach works if accuracy, claim support, calibration and abstention improve over a measured v0 baseline on one frozen 200-question test set (at least 20 unanswerable), with fewer LLM calls and lower cost, each mechanism's gain shows in an ablation, and differences are reported with confidence intervals. A separate 150-question dev set and human-labelled calibration and decision sets are used for tuning; the test set is never used for training or threshold selection.

### 9.1 Objectives and targets

Targets are initial values; the accuracy target is fixed after v0 is measured.

| # | Objective | Metric | Target |
| --- | --- | --- | --- |
| O1 | Correct analysis | Execution accuracy (EX): the executed query returns the reference result | Exceed v0; paired difference with 95% interval reported, no pass/fail test. Provisional target: at least 10 points of EX over v0, fixed after v0 is measured |
| O2 | Faithful explanation | Claim-support rate: numeric and textual claims supported by the result table | At least 0.95 |
| O3 | Calibrated trust | Expected calibration error (ECE) of the confidence badge, with Brier score and reliability plots | At most 0.10, with a bootstrap interval |
| O4 | Appropriate decline | Abstention precision on unanswerable questions, including missing catalogue coverage; recall reported alongside | Precision at least 0.85 |
| O5 | Responsiveness | Time to first streamed event; p95 end-to-end latency | At most 1.5 s; at most 20 s |
| O6 | Efficiency | Cost per answered question; LLM calls per answer | Lower than v0; generation calls only |
| O7 | Visible improvement | Change in EX, ECE, LLM calls and cost across versions | Every version and mechanism reported |
| O8 | Appropriate visuals | Chart appropriateness: the share of answered questions whose chart type matches the rule table for the result shape, rated independently by two team members on a 100-answer sample with disagreements adjudicated by a third; the calibrated chart decision is scored against the same labels | At least 0.90 |

### 9.2 Experiments

| # | Experiment | Comparison | Metrics |
| --- | --- | --- | --- |
| E1 | Version ladder | v0 baseline (fixed workflow; a hosted LLM writes queries and makes every decision; generic prompts) → v1 domain knowledge and retrieval → v2 retrieved verified examples → v3 prompt optimisation (DSPy, GEPA; manual) → v4 fine-tuned Kev replaces the LLM calls for tool selection and domain → v5 calibrated verification and confidence badge → v6 retraining and recalibration after drift | EX with confidence intervals, ECE, LLM calls, cost, latency, error categories |
| E2 | Hosted models and baselines | Two hosted LLMs on the dev set; a general-purpose assistant given the question and table (50-question subset) | EX, JSON validity, claim support, cost, p95 latency |
| E3 | Decision gates and cascade | Per Kev decision (tool selection, domain): zero-shot Kev-0.8B, fine-tuned Kev-0.8B, Jev, the v0 LLM and a Kev-then-Jev cascade; Kev-4B as a stretch comparison. Coverage and chart type are scored on Jev against human labels. The fine-tune, its learning-rate, LoRA-rank, epoch and data-size runs, and the calibration fits are always run and reported. Kev keeps a call only when its calibrated confidence holds expected error at or below 5% | Accuracy, F1, AUROC, Brier score, ECE, share handled by Kev at the 5% budget, latency, cost, LLM calls avoided |
| E4 | Verification | Jev on 150–200 human-labelled instances, with and without calibration; execution-agreement voting; an LLM judge | Accuracy, AUROC, Brier score, ECE with bootstrap interval, risk at a chosen coverage |
| E5 | Ablations and behaviour | Add or remove knowledge, retrieval, examples, prompt optimisation, Kev, verification and thresholds one at a time; 20 or more unanswerable, ambiguous and follow-up questions; clarity and chart ratings | Change in EX, abstention precision and recall, ECE, LLM calls; clarification precision; chart appropriateness |
| E6 | Drift simulation | Injected drift (a burst of new-topic or new-format questions) with simulated users; alert, offline retraining and recalibration, challenger evaluation, admin approval | Time to detect; recovery of EX and ECE; no frozen-set regression |

The retrieval fine-tune is a stretch item (section 4). Its experiment — a general open embedding model, with and without a reranker, against the same model fine-tuned on question–item pairs with whole tables held out, scored by Recall@5 and MRR over verified examples, guidance cards and column descriptions — is retained in the repository and run only if the stretch item is taken. Core retrieval is ablated on and off within E5.

### 9.3 Evaluation rules

- With 200 test questions a score near 50% has a 95% interval of about plus or minus 7 points. Versions are compared on the same questions with paired tests (paired bootstrap or McNemar); the paired difference and its interval are reported and read as evidence, not as a pass/fail significance threshold.
- Thresholds, prompts, temperatures and cascade bands are tuned on the dev set and a separate calibration split, never on the frozen test set.
- Execution accuracy is the primary answer metric; judges and decision models are scored against human labels to avoid circular evaluation.
- Headline ladder results use the shipped configuration (Kev for tool selection and domain; Jev for everything else), with a Jev-only run as reference; development runs may use Jev for speed.
- Kev handles a decision only if its human-label accuracy is within a margin of Jev's fixed beforehand (for example 3 points) and its calibrated ECE is at most 0.10; otherwise the decision stays on Jev and the result is reported as measured. The Kev fine-tune, its learning-rate, LoRA-rank, epoch and data-size runs, and the calibration fits are always run and reported.
- The decision layer is reached through one client with interchangeable backends. The provider, model identifier and access date are recorded with every reported result; any backend or version change triggers a full recalibration and a re-run of the affected rows, and results fitted on different backend versions are never pooled.
- Accuracy and ECE come from one canonical backend, with top-answer agreement across MacBook, CPU and GPU backends checked (target 99%); latency is measured on the GPU endpoint.
- Calibration of the confidence badge is reported with Brier score, reliability plots and bootstrap intervals; with 150–200 labelled instances ECE is noisy and is read with its interval.
- Every API response is cached by request hash, and the frozen test set is run only to produce reported results.
- Success means v6 exceeds v0 on EX with the paired interval reported, meets O2 to O5, and uses fewer LLM calls at lower cost per answer. Because the ladder is cumulative and v0 is deliberately minimal, v6 exceeding v0 is expected by construction and is reported as a sanity check rather than as the finding: the evidential weight sits in E5's one-at-a-time ablations and E3's per-decision gates, which identify which mechanism produced which gain and at what cost. Real traffic will be small, so drift is evaluated with simulated users and injected drift, and the report says so.

## 10. Data, Feasibility and Known Risks

Source data is public. Query writing uses a hosted model, and Kev's training data is generated by rules, construction and a teacher model, so no pre-labelled corpus of questions over Indian tables is needed. The week-1 feasibility test (a hosted LLM answering about 20 questions on 2 tables; Kev-0.8B against Jev on 200 routing examples; a one-hour T4 smoke test, fp16) is designed to confirm this. It has not been run at the time of writing, and its results will be reported as measured.

### 10.1 Sources and training material

**Sources.** data.gov.in (GODL-India; attribution required, and the licence excludes data the provider is not authorised to license, so terms are checked per dataset \[26\]); MoSPI PLFS, CPI, WPI and other series via eSankhyiki (published tables, not microdata; the PLFS design was revamped from January 2025, so series before and after need comparability notes \[24\]\[27\]); and IMD, Ministry of Agriculture (DES), RBI (DBIE) and NFHS (IIPS) tables under each agency's terms, with footnote and total rows, years as columns and mixed units.

The specific 8–12 tables are deliberately not named at this milestone. Candidates are drawn from the sources above; profiling them (row counts, year and geography coverage, missing-value and footnote structure, and whether state rows sum to the All-India row) and freezing the list is the first Milestone 2 deliverable. Quantity and quality claims about the source tables are therefore provisional here.

| Material | Planned size and purpose |
| --- | --- |
| Question and reference-query pairs | 1,000 or more execution-verified pairs, LLM-generated and kept only if the query runs; used as retrieved examples, for prompt optimisation and as test material |
| Routing examples | 1,000–2,000 per Kev decision (tool selection and domain in the core; clarification and intent only if those stretch items are taken): synthetic messages with analysis states, labelled by rules or a teacher model and checked by hand. They measure agreement with the rule or teacher, so every gate is scored on human labels |
| Coverage examples | 150–200 human-labelled questions (answerable cases and unanswerable variants with a shifted geography level, period or measure) calibrate and score Jev's coverage decision; 2,000–3,000 constructed examples only if coverage is fine-tuned (stretch) |
| Retrieval pairs | At least 1,000 question–item pairs derived from the verified set (the example, guidance card and column descriptions the reference query uses), with same-domain hard negatives. Required only for the stretch retrieval fine-tune; core retrieval uses a general open embedding model without training |
| Verification calibration set | 150–200 human-labelled instances (question, executed query, result, correct or not) to calibrate Jev, separate from test data; 2,000–3,000 execution-labelled candidates only if Kev is fine-tuned to verify |
| Evaluation sets | Frozen test set (200 questions, at least 20 unanswerable), dev set (150), 150–200 human-labelled instances per Kev decision; hand-written and verified; the test set is never used for training or tuning |

### 10.2 Is the data enough?

- The scope is narrow (8–12 tables, five domains). Kev's documentation advises starting from a released checkpoint and notes that about 400 records may fall within noise \[7\]; 1,000–2,000 examples per decision is a planning estimate that the data-size runs in E3 test. Reducing the core to two Kev decisions halves this requirement.
- The table list is not yet frozen, so the quantity and quality of the source tables is the one part of this plan that rests on expectation rather than inspection. Profiling the candidates is scheduled first in Milestone 2 precisely so that this is settled before any dependent work begins.
- Label quality matters more than volume: examples whose reference query returns nothing or runs slowly are dropped before labelling.
- The onboarding pipeline contains cleaning risk: profile the file, apply tested cleaning steps only, validate (state rows must sum to the All-India row), then obtain admin approval.
- With few tables, retrieval is scored over verified examples, guidance cards and column descriptions, not tables alone, where recall@5 would sit near its ceiling. That same ceiling is why the retrieval fine-tune is a stretch item and not a core one: the measurable headroom is small, so the training cost is hard to justify inside the core.

**Known risks.** Synthetic questions may be easier or more templated than real ones, so hand-written questions are added to dev and test sets, splits are separated by question template and table, and leakage checks run in Milestone 3. Whole tables are also held out of fine-tuning and retrieval training to test generalisation to newly onboarded data. The provider's terms on using Jev outputs as training labels are unconfirmed; if they do not permit it, labels come from rules and a hosted LLM.

### 10.3 Key risks and fallbacks

| Risk | Mitigation or fallback |
| --- | --- |
| A fine-tuned Kev decision fails its gate | That decision stays on Jev; the cascade escalates uncertain calls; report as measured |
| Kev-0.8B is reported below chance zero-shot on tool routing \[8\], and tool selection is a core decision | Week-1 routing test on 200 examples before the fine-tune is scheduled; the E3 gate reverts tool selection to Jev if the fine-tuned model misses its margin; domain, a closed-set classification, is the safer second core decision |
| Rule or teacher labels measure agreement, not truth; provider terms on using Jev outputs are unconfirmed | Human-labelled dev and test sets; check TypeSafe's terms; otherwise label by rules and a hosted LLM |
| Jev changes access, version or pricing \[5\] | One decision client with interchangeable backends: TypeSafe AI directly, Jev via OpenRouter, and a calibrated hosted-LLM judge on the same labels as the last resort. Provider, model identifier and access date are recorded with every reported result, and any change triggers recalibration and a re-run of the affected rows. Routing stays on Kev |
| GPU access: Qwen3.5 tooling on a T4 (no bf16), and no GPU on the Google Cloud trial account \[28\] | Week-1 smoke test; per-run checkpointing; rented L4 or A100; evaluation on a MacBook; Jev as standby |
| The hosted LLM changes, degrades or becomes costly | Pinned versions; every API response cached; model selection by dev-set comparison; recalibration after any change |
| Cleaning government data takes longer than planned | Limit to 8–12 tables; reusable cleaning steps; freeze the list in Milestone 2 |
| The agent answers from an unrelated table instead of declining | Coverage decision; at least 20 unanswerable test questions; abstention precision tracked |
| Little real traffic; circular or biased evaluation | Simulated users and injected drift, stated openly; execution-based primary metric; judges and decision models scored on human labels \[3\]\[4\] |

## 11. Implementation and Resource Plan

![Core architecture of the agent: a fixed LangGraph workflow with a two-tier decision layer, read-only DuckDB execution over versioned Parquet, and an evidence panel with a calibrated confidence badge](Architecture_Diagram.svg)

*Figure 1. Core architecture. Cross-portal discovery sits in the admin-operated onboarding path at the foot of the diagram, outside the question-answering claim.*

One Compute Engine VM runs the API, UI, admin portal, Postgres with pgvector and a reverse proxy under Docker Compose; DuckDB queries versioned Parquet read-only with a 10-second timeout. Hosted LLM APIs handle query writing, planning and narration; Jev verifies, takes coverage and the other decisions Kev does not handle, and is the standby; Langfuse Cloud (free plan) provides tracing. A free single-container host (a Hugging Face Space) was not adopted, because the plan needs several services.

Kev-0.8B is fine-tuned on a free Colab T4 (rented L4 or A100 as backup); Kev-4B is a stretch comparison. Each run saves a checkpoint to the Hugging Face Hub or Google Drive every epoch, and runs are split across the team members' own accounts. Calibration fits and tests run on a MacBook or CPU; Kev is served from a GPU endpoint for demonstrations if feasible. Core retrieval uses a general open embedding model with an optional reranker and needs no training. The Google Cloud trial cannot attach GPUs to VMs \[28\], so the plan does not depend on them. T4 fine-tuning time is unmeasured (estimate 1–3 hours for Kev-0.8B on 5,000–20,000 short examples) and is one purpose of the week-1 smoke test.

Estimated spend is about US$65–170 to 21 December, of which US$41–83 is credit-eligible under the US$300 Google Cloud credit \[28\]; these are team estimates, and provider prices must be rechecked before use. GPU endpoints run only for demonstrations and reviews, with budget alerts at 50%, 80% and 100% of the credit.

### 11.1 Team and responsibilities

The team has four members and four tracks. Tracks rotate between milestones, and the previous owner of a track reviews the pull requests of the next owner.

| Track | Member | Roll number | Scope |
| --- | --- | --- | --- |
| T1 Data and Tools | Shaoni Samanta | 21f1003157 | Sourcing, profiling, cleaning steps, validation, catalogue, guidance cards, onboarding pipeline, typed tools |
| T2 Agent | Shivanshu Gupta | 22f3002985 | LangGraph workflow, resolvers, query generation, execution, evidence panel, streaming UI |
| T3 Model | Sathya Prakash | 21f1006001 | Kev fine-tuning, calibration fits, gates, retrieval, E3 and Jev integration |
| T4 Ops and Evaluation | Ashmit Ghose | 24f1001827 | Question–reference pairs, splits, leakage checks, human labelling, E1–E6 and reporting, Compose stack, VM, tracing, admin portal, cost monitoring |

Branch naming, the review process and the full responsibility split are recorded in `CONTRIBUTING.md`.

**Next milestone.** Milestone 2 commits to four deliverables: profile the candidate tables and freeze the 8–12 table list; build the cleaned tables and the catalogue for the first two or three of them; report the week-1 feasibility results (a hosted LLM on about 20 questions over 2 tables, Kev-0.8B against Jev on 200 routing examples, and the T4 smoke test); and produce the first question–reference pairs with a dev and test split separated by table and template. The remaining pair generation, the leakage checks and the human-labelled calibration and decision sets follow in Milestone 3.

## 12. References

All links were opened on 21 or 22 October 2026. Items 5, 7 to 11, 21 and 22 are vendor or project documents whose performance figures are self-reported. Item 25 reports the portal's own statistics as shown on 22 October 2026.

1. Guo, C. et al. (2017). [On Calibration of Modern Neural Networks](https://arxiv.org/abs/1706.04599). ICML 2017.
2. Kadavath, S. et al. (2022). [Language Models (Mostly) Know What They Know](https://arxiv.org/abs/2207.05221). arXiv:2207.05221.
3. Zheng, L. et al. (2023). [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685). NeurIPS 2023 Datasets and Benchmarks.
4. Verga, P. et al. (2024). [Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models](https://arxiv.org/abs/2404.18796). arXiv:2404.18796.
5. TypeSafe AI (2026). [Introducing System One Models and Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev). Vendor blog; early access.
6. TypeSafe AI. [API documentation: System One endpoint](https://docs.typesafe.ai/api); [OpenAPI schema](https://api.typesafe.ai/openapi.json).
7. [Kev: small open decision models on Qwen3.5](https://github.com/jaredpalmer/kev) (jaredpalmer/kev). Project README.
8. [Kev-0.8B model card](https://huggingface.co/jaredpalmer/kev-0.8b). Hugging Face.
9. [Laya](https://pypi.org/project/laya/). Project documentation on PyPI.
10. Contrastive-LM. [CLM-v0.1-8B](https://huggingface.co/Contrastive-LM/CLM-v0.1-8B). Hugging Face model card.
11. CobuildX-AI. [RubriX-8B](https://huggingface.co/CobuildX-AI/RubriX-8B). Hugging Face model card.
12. Cobbe, K. et al. (2021). [Training Verifiers to Solve Math Word Problems](https://arxiv.org/abs/2110.14168). arXiv:2110.14168.
13. Lightman, H. et al. (2023). [Let's Verify Step by Step](https://arxiv.org/abs/2305.20050). arXiv:2305.20050.
14. Geifman, Y. and El-Yaniv, R. (2017). [Selective Classification for Deep Neural Networks](https://arxiv.org/abs/1705.08500). arXiv:1705.08500.
15. Wen, B. et al. (2025). [Know Your Limits: A Survey of Abstention in Large Language Models](https://arxiv.org/abs/2407.18418). TACL 2025; arXiv:2407.18418.
16. Radhakrishnan, P. et al. (2024). [Knowing When to Ask: Bridging Large Language Models and Data](https://arxiv.org/abs/2409.13741) (DataGemma). arXiv:2409.13741.
17. Huang, Y. et al. (2024). [DA-Code: Agent Data Science Code Generation Benchmark for Large Language Models](https://arxiv.org/abs/2410.07331). EMNLP 2024.
18. Hu, X. et al. (2024). [InfiAgent-DABench: Evaluating Agents on Data Analysis Tasks](https://arxiv.org/abs/2401.05507). arXiv:2401.05507.
19. Khattab, O. et al. (2023). [DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines](https://arxiv.org/abs/2310.03714). arXiv:2310.03714.
20. Agrawal, L. A. et al. (2025). [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457). ICLR 2026 (Oral, per arXiv).
21. Snowflake (14 August 2024). [Snowflake Cortex Analyst: Behind the Scenes](https://www.snowflake.com/en/engineering-blog/snowflake-cortex-analyst-behind-the-scenes/). Vendor blog.
22. Databricks. [Genie documentation](https://docs.databricks.com/aws/en/genie/). Vendor documentation.
23. Press Information Bureau, MoSPI (6 February 2026). [NSO Launches MCP Server to Make Government Data AI Ready](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2224472&reg=3&lang=1).
24. Press Information Bureau, MoSPI (23 March 2026). [Government has introduced a Model Context Protocol server to facilitate linking of Artificial Intelligence tools with Official Statistical databases](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2243781&reg=3&lang=2).
25. Open Government Data (OGD) Platform India. [Home page statistics](https://www.data.gov.in/) (accessed 22 October 2026).
26. Open Government Data Platform India. [Government Open Data License - India](https://www.data.gov.in/Godl).
27. National Statistics Office, MoSPI. [Unit-level data of PLFS, monthly (April to December 2025)](https://microdata.gov.in/nada/index.php/catalog/291). Online Microdata Library.
28. Google Cloud. [Free Google Cloud features and trial offer](https://docs.cloud.google.com/free/docs/free-cloud-features).
29. Chen, L., Zaharia, M. and Zou, J. (2023). [FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance](https://arxiv.org/abs/2305.05176). arXiv:2305.05176.
30. Ong, I. et al. (2024). [RouteLLM: Learning to Route LLMs with Preference Data](https://arxiv.org/abs/2406.18665). arXiv:2406.18665.
31. Ross, H., Mahabaleshwarkar, A. S. and Suhara, Y. (2025). [When2Call: When (not) to Call Tools](https://arxiv.org/abs/2504.18851). NAACL 2025.
32. Yao, S. et al. (2023). [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629). ICLR 2023.
33. Yu, T. et al. (2018). [Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task](https://arxiv.org/abs/1809.08887). EMNLP 2018.
34. Li, J. et al. (2023). [Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs](https://arxiv.org/abs/2305.03111). NeurIPS 2023; arXiv:2305.03111.
35. Pourreza, M. and Rafiei, D. (2023). [DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction](https://arxiv.org/abs/2304.11015). NeurIPS 2023; arXiv:2304.11015.
36. Talaei, S. et al. (2024). [CHESS: Contextual Harnessing for Efficient SQL Synthesis](https://arxiv.org/abs/2405.16755). Preprint; arXiv:2405.16755.
