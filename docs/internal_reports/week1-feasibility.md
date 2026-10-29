# Week-1 feasibility checks

Branch `feature/week1-feasibility`, results dated 2026-10-23. All routing figures are
**preliminary**: the 200 routing labels were written by a teacher model and are not yet
human-checked (`human_checked: false` in `data/sample/routing_week1.jsonl`). The checks are
repeated after the labels are validated.

## Summary

| Check                                            | Status                 | Result                                                                  |
| ------------------------------------------------ | ---------------------- | ----------------------------------------------------------------------- |
| Kev-0.8B zero-shot vs Jev, 200 routing examples  | Done, preliminary      | Kev 0.42 accuracy, Jev 0.815. The 3-point margin is not met zero-shot.  |
| Hosted LLM answers 20 questions on 2 tables (v0) | Harness ready, not run | No LLM provider or key is configured.                                   |
| Compose stack behind Caddy streams SSE           | Done                   | Events arrive unbuffered; two defects in the Caddy configuration fixed. |
| Kev fine-tune dry run locally                    | Done, functional only  | Pipeline runs end to end; no accuracy claim.                            |

## 1. Data used

Two tables from the Open Government Data Platform India (Government Open Data License - India),
retrieved 2026-10-23 (identifiers and licence in `data/sample/README.md`):

- `imd_subdivision_monthly_rainfall`: IMD monthly rainfall, 36 sub-divisions, 1901-2017, 4,188 rows.
- `plfs_state_ur_usual_status`: PLFS unemployment rate, usual status, persons aged 15 and above,
  37 States/UTs plus an `All India` row, survey years 2017-18 to 2021-22, years as columns.

Features retained deliberately: sub-divisions instead of states, `Orissa` against `Odisha`, `NA`
strings, an aggregate row, calendar years against July-June survey years. The catalogue also holds
a near-duplicate PLFS resource and an all-ages variant of the same series.

## 2. Routing: Kev-0.8B zero-shot against Jev

Setup: six tools, one yes/no (noul) question per tool, the tool with the highest yes-probability is
the prediction. Kev-0.8B served locally (Apple M5, MPS, fp32, `KEV_TEMPERATURE=1.0`, raw
probabilities); Jev is `jev-latest` through the TypeSafe API. Identical prompts and examples for
both. One prompt wording was tried; zero-shot results are sensitive to wording.

| Measure                            | Kev-0.8B zero-shot      | Jev                                |
| ---------------------------------- | ----------------------- | ---------------------------------- |
| Accuracy (95% bootstrap interval)  | 0.42 (0.35-0.49)        | 0.815 (0.76-0.87)                  |
| Macro-F1                           | 0.36                    | 0.80                               |
| ECE, uncalibrated (see note)       | 0.20                    | 0.38                               |
| Latency per decision, median / p95 | 1.66 s / 1.94 s (local) | 0.31 s / 0.63 s (includes network) |
| Chance (uniform / majority class)  | 0.17 / 0.225            | 0.17 / 0.225                       |

- Paired difference, Jev minus Kev: 39.5 points (95% interval 32-47). Both correct 80, only Jev
  83, only Kev 4, neither 33.
- Kev over-predicts `ask_clarification` (68 predictions against 38 labelled) and almost never
  predicts `decline_not_covered` (2 against 32). Per-tool F1 is best for `make_chart` (0.81) and
  `run_sql` (0.63).
- Jev per-tool F1: `make_chart` 1.00, `describe_table` 0.88, `run_sql` 0.86, `ask_clarification`
  0.83, `decline_not_covered` 0.69, `search_catalog` 0.54.
- Note on ECE: the confidence used is the chosen tool's share of the summed yes-probabilities.
  Each tool question is answered independently, so this share is not a calibrated probability and
  the ECE values are not comparable with a fitted temperature. Calibration is a later step.
- Jev reports billable input tokens per call (output tokens are free of charge). The client now
  records them; cost per 1,000 decisions will be reported on the re-run. No price has been confirmed.

**Consequence for the plan.** The gate in the adopted plan (Kev within 3 points of Jev) is not met
by the zero-shot model. The Kev card reports below-chance zero-shot accuracy on this kind of
routing (self-reported; not independently verified); the measured accuracy is above chance but
far below Jev. Whether a fine-tune closes a gap of
roughly 40 points is untested and is decided by the fine-tune and the E3 gate. The week-1 evidence
supports keeping Jev as the tool-selection model until then.

**Boundary problem in the label definitions.** Jev sent 17 of 27 `search_catalog` examples to
`decline_not_covered`, for instance "Search for datasets about wages." and "Which dataset would
tell me about groundwater levels?". The tool definitions overlap for topics outside the catalogue:
the router may search for a dataset or decline. The labels need a rule before the re-run.

## 3. Label review

A second, blind pass (the reviewer saw questions, not labels) agreed with the teacher labels on
198 of 200 items; the disagreements are `rb-032` and `rb-064`. Agreement between two passes from
the same model family is not validation. Human review is required before results count. Ids
flagged as judgement calls by the label authors: `ra-052`, `ra-076`, `ra-079`, `ra-081`, `ra-089`,
`ra-091`, `rb-032`, `rb-034`, `rb-037`, `rb-052`, `rb-053`, `rb-064`, `rb-077`, `rb-080`,
`rb-094`, `rb-098`; the 17 `search_catalog` items sent to `decline_not_covered` by Jev are
affected by the boundary problem above.

## 4. Hosted-LLM v0 on two tables

Not run. `LLM_API_KEY`, `LLM_MODEL` and `LLM_BASE_URL` are unset and the provider is undecided.
Implemented and tested without a provider:

- `analyst.tools.sql_runner`: single `SELECT` only (sqlglot), tables restricted to the catalogue,
  table functions and file access rejected, 10 s timeout; 16 tests pass; all 18 reference
  queries are accepted.
- `analyst.evaluation.v0_eval`: OpenAI-compatible client, execution-result comparison (rounded,
  order-insensitive unless the reference sorts), decline handling, failure categories, token counts.
  With stand-in models: reference-SQL oracle 1.00, decline-everything 0.10, wrong SQL 0.00.

## 5. Compose stack and SSE through Caddy

All five services start (ui, api, admin, db, caddy) on Docker Desktop 29.9.2. With a 1.5 s pause
between placeholder events, events arrive at 0.02-0.04 s, 1.5 s and 3.0 s: no buffering; first
byte 7 ms with `Accept-Encoding: gzip`. These are placeholder events on localhost, not agent
output, so the O5 target (first event within 1.5 s) is not yet tested end to end.

Defects found and fixed in `infra/caddy/Caddyfile`:

1. The `@sse` rule was never reached, because `handle_path /api/*` is evaluated first; streaming
   worked only through Caddy's automatic flushing of `text/event-stream`. The rule is removed and
   `flush_interval -1` is set on the `/api/*` proxy.
2. The comment stated that `localhost` serves plain HTTP. Caddy redirects to HTTPS with an
   internal certificate (HTTP 308); the comment now says so (`curl -k`, or `http://localhost`).

`app/api/main.py` gained `STREAM_EVENT_DELAY_S` (default 0.1) to make buffering observable.

## 6. Kev fine-tune dry run (MPS)

64 routing examples (every third, all six tools, unchecked labels), `--init_from jaredpalmer/kev-0.8b`
(372 LoRA tensors and the pointer head loaded), LoRA rank 16, learning rate 2e-5, fp32, batch 1,
accumulation 4, checkpointing on, `--max_steps 4`.

| Measure                                  | Value                                                 |
| ---------------------------------------- | ----------------------------------------------------- |
| Optimizer steps / records seen           | 4 / 16                                                |
| Time per optimizer step                  | about 28-36 s                                         |
| Peak device memory / peak process memory | 3.29 GB / 2.44 GB                                     |
| Mean gradient norm                       | 9.9; all 4 steps clipped                              |
| Checkpoint                               | 62 MB (`models/checkpoints/week1_dry`, not tracked) |

- No accuracy is claimed; four steps establish only that the data format and training loop work.
- The trainer offers `--dtype fp32|bf16` and `--weights_dtype fp32|bf16`; there is no fp16 option,
  and bf16 autocast is documented as CUDA-only. A T4 run would therefore use fp32 for both. The
  device memory above suggests this fits in the T4's roughly 15 GB (estimate; not tested on a T4).
- Extrapolating 7.5 s per record gives roughly 4 hours for 2,000 records on this Mac (estimate from
  four steps); the real run is planned on Colab.
- `causal_conv1d` and `flash-linear-attention` are not installed, so reference kernels were used.

## 7. Open items from this branch

1. Rule for `search_catalog` against `decline_not_covered` for topics outside the catalogue.
2. Human validation of the 200 routing labels and of the 20 v0 reference answers' assumptions
   (notably `v0-16`, Karnataka has three sub-divisions); then repeat the routing evaluation.
3. LLM provider, model and key for the v0 run; Jev unit price for the cost figures.
4. Compare the served calibrated probabilities (default) with the raw ones used here.
5. Fine-tuned Kev on the validated routing set (Colab T4, fp32).

## Reproduction

```
python -m analyst.evaluation.routing_eval run --backend kev --out outputs/week1/routing_kev.jsonl
python -m analyst.evaluation.routing_eval run --backend jev --out outputs/week1/routing_jev.jsonl
python -m analyst.evaluation.routing_eval score outputs/week1/routing_kev.jsonl
python -m analyst.evaluation.v0_eval run --out outputs/week1/v0_<model>.jsonl
```

Raw predictions are written to `outputs/week1/` (not tracked).
