# Changelog

Entries follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions track the evaluation ladder: `v0` baseline through `v6` retraining and
recalibration, as defined in [docs/milestones/Milestone1_Report.md](docs/milestones/Milestone1_Report.md).

## [Unreleased]

### Added

- Repository scaffold: package layout under `src/analyst`, application
  directories, configuration, infrastructure and test directories.
- Project metadata: `pyproject.toml`, `LICENSE`, `CONTRIBUTING.md`, this file.
- Docker Compose stack: `ui`, `api` (API and agent), `admin`, Postgres with
  pgvector, and Caddy.
- Milestone 1 report, architecture diagram and TA presentation deck under `docs/`.
- `WORKLOG.md`, required by the course guidelines: individual contributions,
  updated weekly.
- Repository structure and `README.md` aligned to the course guidelines
  (https://bsc-iitm.github.io/dsai-lab-project/guidelines.html): `outputs/`
  and `models/` subfolders, named test stubs, README sections for features,
  dataset, models, results, demo and team members.

- Milestone 2 (29 October 2026): report `docs/milestones/Milestone2_Report.md` with document change
  log, contribution log and sign-off; five cleaned tables (IMD rainfall, PLFS, NFHS-5,
  Mandi, NCRB); EDA (`scripts/eda_tables.py`, `docs/milestones/figures/milestone2/`); data manifest
  with SHA-256 (`data/MANIFEST.md`); routing splits v1 tracked under `data/splits/kev/`;
  text-to-SQL reference pairs split by template into dev (63) and test (37).

- Reusable data preparation (3 November 2026, Milestone 2 resubmission): one pipeline driven by
  a config per table (`configs/sources/`) in place of per-table scripts; shared observation
  tables (`obs_<dataset>`) with a quality flag, original text and rule ids on every value for
  all five datasets; review list and suggested fixes instead of silent corrections; approved
  header snapshots and drift checks; generated `catalogue.json` and `dim_period`; lineage log
  and manifest with raw checksum, config version and code commit; fault-injection and
  rebuild-equality tests (`tests/`). Specification in `docs/specs/data_contract_v1.md`.
- Handling of changes in public data (3 November 2026, contract 1.1): year windows that change
  over time (`period.conventions`, `period.exceptions`, `period.verified_through`), overlap and
  gap checks on periods, a `quarter` period type, comparison of each release with the live one
  of the same dataset with accepted changes recorded in the lineage, place names matched
  ignoring case and spacing, sub-division aliases, single-year period headers, a warning for
  checks that name a missing column, and `scripts/robustness_sweep.py`.
- Candidate tables (5 November 2026, T1): source record `docs/specs/candidate_tables.md` for the ten
  T1 tables and the four `data_discovery` files (resource ids, publishers, periods, units, place
  spellings, quirks, decisions); `scripts/download_raw.py` covers the ten tables and accepts file
  names to download only those; raw-file list in `data/README.md`.
- Agent design, base version (T2 and T4): `docs/Langgraph diagram.md`, the node graph from which
  `docs/specs/agent_graph.md` version 0.1 was derived.
- Milestone 3 (5 November 2026): report `docs/milestones/Milestone3_Report.md` and slides
  `docs/milestones/Milestone3_TA_Presentation.pptx`; agent graph specification
  `docs/specs/agent_graph.md` (version 0.3); phase 1 of the Kev adoption, the domain decision:
  `src/analyst/decisions/phase1.py`, `scripts/build_domain_phase1.py`,
  `src/analyst/evaluation/domain_eval.py` (temperature fit, paired bootstrap),
  `scripts/domain_phase1_eval.sh`, choice-question support in `system_one.py`; an end-to-end
  slice over the five tables, `src/analyst/pipelines/end_to_end_slice.py`; tests
  `tests/test_domain_phase.py` and `tests/test_end_to_end_slice.py`.
- Jev zero-shot reference on the domain decision (5 November 2026): accuracy 0.929 on the 338
  dev-synthetic items (`outputs/reports/domain_jev_score.json`).
- RAG proof of concept (10 November 2026, response to the Milestone 3 review): knowledge entries
  and hybrid retrieval (`src/analyst/retrieval/knowledge.py`, `hybrid.py`: BM25 and
  `bge-small-en-v1.5` in Postgres with pgvector, reciprocal rank fusion); hosted LLM client over an
  OpenAI-compatible endpoint (`src/analyst/inference/llm.py`); ten-node LangGraph graph with a
  coverage check, guarded SQL with one repair, result checks and a number check before release
  (`src/analyst/pipelines/rag_poc.py`); guidance and analysis cards
  (`configs/rag/guidance_cards.v0.json`); verified examples and a 12-question set
  (`data/sample/rag_*.v0.jsonl`); `scripts/rag_poc_db.sh`; `tests/test_rag_poc.py`.
- Milestone 3 report version 1.2 (10 November 2026): response to the review, end-to-end run
  (Section 8.5), RAG pipeline (Section 9), end-to-end success rate (Section 7.4), reproduction
  steps (Appendix A). Every output file cited in the report is now committed under `outputs/`.
- Reproducibility of the RAG proof of concept (10 November 2026): embedding model pinned by
  revision, pgvector image pinned by digest, run metadata (git commit, package versions, model
  names, served model version) in every output record, `requirements.lock.txt` with the exact
  environment; repeat run `outputs/predictions/rag_poc_flash_lite_run2.jsonl` (11 of 12; retrieval
  identical, SQL differed in 6 of 12). Milestone 3 report and slides: file references are links,
  open items moved to Milestone 4, version 1.2 sign-off recorded.

- Milestone 4 integration (18-19 November 2026, branch `docs/milestone-4`). Each item states the
  general behaviour; the case that revealed it is given in brackets.
  - Integration of the T4 tool layer and evaluation tooling with the T2 graph and the T3 model
    nodes; offline dry-run harness (scripted model replies, gold SQL) and live development runs
    on `e2e_dev` (success 0.45, 0.80 and 0.875 on successive code versions; see Notes).
  - Catalogue retrieval covers every table and indicator: place slot (gazetteer of districts,
    sub-divisions and markets), indicator slots, Hindi and Hinglish query glossary, widened
    search; audit of 1,148 generated questions (all found) and 60 paraphrases.
  - Charts: Vega-Lite specification chosen by column role (period, measure, entity, or the
    indicator, sector or category column when place and period are the same); line for
    periods, bars for places or groups, ranked bars for rankings; `--save-chart` answer pages.
  - Conversation memory of the last five turns (question, reading, outcome, start of the
    answer); intent prompt v8 resolves references to any of them into explicit mentions, marks
    each question as a follow-up or a new question (a new topic carries nothing over) and
    writes a standalone question used by narration and logs.
  - Replies to a clarification read by code against the offered options before any model sees
    them: by position ("second one", "2", "last"), by words, "yes" when one option was offered,
    "all" or "both", "none of these", or a new question; the router and decision models
    receive one complete question. Options are numbered.
  - Written replies on branches without a query: a decline where no table fits states what the
    catalogue covers and is classified as a data request (logged), a message outside the scope
    (not logged) or personal distress (a fixed national helpline line is added by code); a
    definition question is answered only from the catalogue entries and guidance notes, or
    states that the term is not documented. Every number in such a reply must appear in its
    inputs.
  - Decision-backend variants in `configs/inference.yaml` without changing the version ladder:
    `jev_routing` puts tool and domain on Jev with the hosted LLM as fallback; recorded in the
    run configuration and every prediction row.
  - API service (`app/api/main.py`): `/ask`, `/stream` (server-sent events per graph step),
    `/conversations/{id}`, `/healthz`; demo page `app/ui/static/index.html` (answer first,
    options, chart, one collapsed Details section with interpretation, evidence, SQL and steps).
  - Implicit-caching layout of the intent prompt (fixed catalogue block first); cached input
    tokens recorded when the provider reports them.

### Changed

- `.gitignore` (5 November 2026): exception for `configs/reference/*.csv`, which the data
  pipeline and 55 tests need and which were not tracked.
- Data preparation (3 November 2026): IMD and PLFS now carry `quality_flag` and `rule_ids`;
  place names the old alias list left unstandardised (`Maharastra`, `Jammu & Kashmir`,
  `Dadra and Nagar Haveli & Daman and Diu`, `Chattisgarh`, `Andaman and Nicobar`) are now
  standardised in `state_name`, source spellings kept; quality flags use one shared
  vocabulary (`missing_or_unparseable` is `unparsed`, `invalid_price_order` is `inconsistent`,
  `passed` is `reported`). Reference queries `Q025` and `Q059` use the new flag names; all
  90 executable reference queries return the same results as before.
- Preprocessing script runs from any directory; NFHS-5 cells exported as negative numbers
  are read as low-sample estimates; Mandi rows with implausible prices are flagged.
- Reference queries `Q012` and `Q019` corrected to match the prepared NFHS-5 labels.
- Milestone 1 report revised (27 October 2026) in response to TA feedback:
  - Refined the problem statement, research questions and project scope.
  - Strengthened the literature review; clarified research gaps and the proposed contribution.
  - Clarified the system architecture, decision-model roles and baseline comparisons.
  - Defined end-to-end correctness, confidence calibration, evaluation metrics and abstention criteria.
  - Added a failure taxonomy distinguishing data limitations from system errors.
  - Expanded the evaluation plan, dataset requirements, feasibility checks, risks and Milestone 2 deliverables.
  - Verified by 
    - Shivanshu Gupta (22f3002985), 27 October 2026.
    - Sathya Prakash (21f1006001), 27 October 2026.

- Milestone 4 integration (18-19 November 2026):
  - Resolution defaults applied by code and stated in the answer: national mentions resolve to
    the national row; a category column whose codelist holds a total value (Total, All,
    Rural+Urban, Persons, Combined) defaults to it; a single-period question without a period
    uses the latest complete period.
  - A follow-up inherits the slots it does not name from the previous plan, only when the
    intent marks it as a follow-up.
  - Search is widened after a not-covered result only when the intent names a catalogue table
    outside the candidates, and then only that table (five of six widened searches in a dev run
    repeated a decline or a period gap).
  - A chart request reuses the stored result only when it can be plotted; otherwise the values
    to plot are queried with the conversation history.
  - Value quality: implausible values are a query fault; suppressed, low-sample and missing
    values become caveats. Retry hints name each failed check.
  - Narration states the unit once, a long series in one sentence, and names each yearly
    period by its start month (fiscal year April to March, survey year July to June).
  - Prompt versions: intent v8, SQL v3, narrate v2, clarify v2, route v2; new prompts decline v1
    and describe v1. Earlier versions are kept for provenance.
  - Evaluation: execution accuracy on the gold columns within a wider result; entity columns
    and series end points in scoring; `out_of_scope` counts as a correct decline; `e2e-079` and
    `e2e-092` relabelled as answers with gold SQL (split frozen, files edited in place, hashes
    in `configs/evaluation.yaml`).
  - Hosted-model access through an impersonated service account; access token cached for 45
    minutes with a bounded token fetch; request timeout 12 s; embedding model loaded offline.

### Fixed

- Milestone 4 integration (18-19 November 2026):
  - Run log: a model call that failed every attempt stopped the run from being logged (it went
    to `outputs/runs/failed/`); such runs are now logged, and earlier ones were replayed.
  - Place names match with spaces ignored and suggest close names ("Tamilnadu"); a State or
    district filters a finer table also when the question names the finer level.
  - Periods: numeric months (`2020-03`, `3/2020`) on monthly tables; season labels in the
    table's own form (`2016-JJAS`), with the season codes read from each table's data; an
    unresolved period offers the table's latest periods, not its period-type names.
  - A period stated relative to today after the end of the data is declined with the reason.
  - A clarification with one fitting measure answers with it and states the assumption; a
    missing population group is always asked.
  - A model reply placed reasoning in the standalone-question field; such text is dropped.
  - Narration cut off at the output cap for long series; cap raised and reply shortened.
  - Number parser: bare years, digit grouping and "per N" denominators.
  - Charts drawn with zero width in the demo page; explicit width and page-themed colours. A
    chart of several measures with one unit shows that unit; long category labels are kept.
  - A definition question that asks for figures ("comment on all the categories" after an
    answer) continues on the query path; definitions start from the previous turn's table and
    read the recent history; the fallback summary covers the right table and states coverage as
    first to last period. Output caps of the decline and describe replies raised (the model's
    thinking used the whole cap).
  - Clarification options for a population group leave out columns that already default to a
    total (an age-group question no longer offers Rural, Total and Urban).
  - SQL validation checks that every indicator id in the query belongs to the plan; another id
    (one invented by editing the planned id matched no row and led to a slow regeneration)
    goes to repair before execution. Regeneration thinking lowered from medium to low (about
    10 s against a 12 s request timeout had exceeded the run deadline).
  - Charts: the column that tells rows apart is found from the result (plan category columns,
    then indicator columns, then any varying text column), and a chart is never drawn when two
    rows fall on one position (three area values had been stacked into one bar); such results
    are shown as a table.
  - Narration states when compared groups are nested (an age range inside a wider one, a total
    and its parts).
  - Version ladder (19 November): retrieved content contradicted the rules code enforces, which
    lowered v1 and v2 below v0. Guidance cards (v2, v3) state facts and never tell the model to
    ask or to report every variety; verified examples (v2) follow the SQL prompt's rules; tests
    check both. v2 routes tool and domain on Jev.
  - Reliability: access token aged by wall-clock time with a refresh on 401/403; longer pause on
    HTTP 429; intent cap 1024, request timeout 20 s, run deadline 45 s; a reply that loops or is
    cut at the cap keeps its complete fields; indicator ids repaired by hash suffix or, when one
    indicator fits, by label words.
  - A follow-up that asks for new figures after an explanation request continues on the query
    path. A single-place question with no place named, on a table without a national row, is
    asked. A single-value question whose rows would differ in an unnamed category with a small
    closed set of values (MSP variety, crop season) is asked. Category values that do not exist
    in their column, or repeat another column's value, are dropped.
  - Evaluation: 20-item dev supplement (describe, search, clarify, decline, multi-turn) written
    by T3; e2e_v1 and its test split unchanged; success by expected action in the ladder table.

### Notes

- Milestone 2 (29 October 2026): no model, agent or tool code was implemented yet; the
  milestone froze the table list and delivered the first cleaned tables and catalogue.
- Milestone 4 development runs on `e2e_dev` were made while fixing the agent against that set,
  so they are optimistic; the version comparison is reported from repeated runs on frozen code,
  and `e2e_test` is never used for tuning.
- Milestone 4 version ladder (19 November 2026), frozen commit `a2c8c7d`: dev confirmation of
  1 run per version on `e2e_dev` plus `e2e_dev_extra` (60 questions) and a test ladder of 3 runs
  per version on `e2e_test` (60 questions), versions v0, v1 and v2 (v2 routes with Jev). Inputs:
  `outputs/predictions/final_{dev,test}_*`; tables: `outputs/reports/version_ladder_{dev,test}.md`
  (scorer rules v2) and `outputs/reports/version_ladder_{dev,test}_scorer_v1.md` (scorer rules v1). Gold is checked by T3; T1 validation is pending.
- Scorer rules v2 (`e2e_eval score --scorer v2`, now the default), added after the test ladder:
  an expected entity may be a category value of a result row, or a place plus a category value
  ("Bihar Rural"), and tables named in a search or describe reply count as found. The saved
  predictions were re-scored without new runs; this is a post-hoc scorer change, reported beside the as-run v1 figures, and no agent change
  was made from test items. `--scorer v1` reproduces the as-run tables (`*_scorer_v1`).
