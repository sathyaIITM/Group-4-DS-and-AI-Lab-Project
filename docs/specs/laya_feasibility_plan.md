# Laya fine-tuning: smoke run and feasibility plan (Milestone 4)

Version 1.0, 17 November 2026. Owner: T3. Purpose: a fine-tuned Laya row for the domain decision,
as a comparator to the selected Kev-0.8B checkpoint. Laya is trained with its default recipe and
is not tuned. The report states this, so the row is not read as an equal-effort comparison.

## 1. Facts checked on 17 November

| Item | Finding | How it was checked |
| --- | --- | --- |
| Package | `laya` 0.4.23, Apache-2.0 | Package metadata of the installed copy |
| Model | ModernBERT-large encoder, about 421M parameters (self-reported) | Model card; not re-measured |
| Trainer flags | `--device auto/cpu/cuda/mps`, `--eval` (before and after scoring), `--dry-run`, `--loss rlcd` (default) or `soft-ce`, `--epochs 4`, `--micro-batch 8`, `--grad-accum 8`, `--encoder-lr 2.5e-5`, `--head-lr 1e-4`, `--seed`, `--max-len` | `laya-train --help` |
| Internal hold-out | 10% of the training rows are held out to fit abstention thresholds (`calib_frac = 0.1`) | `laya/train.py:109` |
| Long states | The state is capped at `max_len` tokens (truncated, not dropped); the default comes from the checkpoint configuration | `laya/train.py:287-290` |
| Our data | Dry run on `laya_domain/train.v2.jsonl`: 1,876 of 1,876 rows valid, 1,689 used for training after the hold-out, 108 optimizer updates over 4 epochs; `dev_synthetic.v2`: 355 of 355 valid | `laya-train --dry-run` (command in Section 3) |
| Serving | `laya-serve` needs the `serve` extra (FastAPI, uvicorn), which the cached environment lacks | `laya-serve` start-up error |

The training rows are written by `scripts/build_domain_phase1.py --version v2 --laya`
(`phase1.to_laya_row`): the same state and question text as the Kev records, with the label
moved to `expected`. Hashes are in `data/MANIFEST.md`.

## 2. Open questions for the smoke run

1. Does training run on the local machine (MPS), and at what speed per optimizer update?
2. Peak memory on the local machine (16 GB shared).
3. How many states exceed Laya's token budget (and are therefore truncated)?
4. Can `laya-serve` load a local fine-tuned checkpoint (variables `LAYA_MODELS`,
   `LAYA_DEFAULT_MODEL`), so that `decision_eval run --model laya` scores it on the same route as
   Kev? If not, the predictions are collected with the package's Python API.

## 3. Commands

Environment, pinned version with the serve extra (no account or spend):

```bash
uv tool install 'laya[serve]==0.4.23'
```

Dry run (done on 17 November; repeatable):

```bash
laya-train --data data/splits/laya_domain/train.v2.jsonl \
  --eval data/splits/laya_domain/dev_synthetic.v2.jsonl --out /tmp/laya_dry --dry-run
```

Smoke run, local machine, 32 rows, 1 epoch, timed:

```bash
/usr/bin/time -l laya-train --data data/splits/laya_domain/overfit32.v2.jsonl \
  --eval data/splits/laya_domain/calibration.v2.jsonl --out models/checkpoints/laya_smoke \
  --epochs 1 --device mps --seed 0 2>&1 | tee outputs/logs/laya_smoke.log
```

Full run (only if Section 4 passes), default recipe:

```bash
/usr/bin/time -l laya-train --data data/splits/laya_domain/train.v2.jsonl \
  --out models/checkpoints/laya_s0 --micro-batch 2 --grad-accum 32 \
  --device mps --seed 0 2>&1 | tee outputs/logs/laya_s0.log
```

Scoring follows the Kev procedure on the same files: predictions on `calibration.v2` and
`dev_synthetic.v2`, the temperature fitted on calibration, and `decision_eval score`. After the
freeze, `dev_human` is scored once. Laya's own abstention thresholds are not used. Its
probabilities are scaled by the same temperature method as Kev's, so both rows are calibrated
the same way.

## 4. Smoke results (17 November)

- With `--eval` on the calibration split, the run ran out of MPS memory in Laya's
  pre-training evaluation (batch 16) after 640 s, before any training step
  (`outputs/logs/laya_smoke.log`).
- Without `--eval` and with `--micro-batch 2 --grad-accum 32` (the same effective batch of 64
  as the default 8 x 8), the run passed in 29 s (`outputs/logs/laya_smoke_b.log`). The full run
  therefore uses these two settings; evaluation is done by our scoring, not by `--eval`.
- Projection for the full run: 1 to 2 hours on the local machine (estimate; 233 times the
  smoke's item passes, and the smoke time includes model loading).
- Open: the scoring route (batch size or `laya-serve`) and the truncation count.
  Record: `outputs/reports/laya_feasibility.json`.

## 5. Feasibility criteria (decided before the smoke run)

| Criterion | Pass | Otherwise |
| --- | --- | --- |
| Smoke run completes on MPS | Exit code 0; checkpoint written | Run the same command on the spare Kaggle GPU (`--device cuda`) |
| Projected full run (smoke time per update x 108 updates) | At most 3 hours on the local machine | Kaggle GPU slot |
| Truncated states | At most 1% of rows | Report the share; consider `--max-len` within the checkpoint limit |
| Scoring route | `laya-serve` serves the checkpoint, or the Python API returns probabilities for every option | Drop the fine-tuned row; keep the zero-shot row and record the reason |

The outcome is recorded in `outputs/reports/laya_feasibility.json`, with the smoke log, the wall
time, peak memory, the truncation count and the decision. The Milestone 4 report cites that file.
Runs: 1 seed is planned. Seeds 1 and 2 are added only if compute remains, as with the deferred Kev
runs.
