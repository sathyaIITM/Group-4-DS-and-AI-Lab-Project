# Kev-0.8B domain training protocol (Milestone 4)

Version 1.1, 17 November 2026 (1.1: changes after the external code review, Section 9). Owner: T3. Scope: phase 1 of the Kev adoption, the domain
decision. Tool selection stays on Jev until phase 2. This file fixes the runs, the procedure, the
checkpoint-selection rule and the records that the Milestone 4 report cites. It is written before
any planned run is trained and before the dev_human labels are frozen.

## 1. Data

| File | Records | SHA-256 | Use |
| --- | --- | --- | --- |
| `data/splits/kev_domain/train.v2.jsonl` | 1,876 | `bd762f0f…7e79a54f` | Training |
| `data/splits/kev_domain/calibration.v2.jsonl` | 322 | `8d363f6e…0c3bdcba` | Temperature fit; validation loss |
| `data/splits/kev_domain/dev_synthetic.v2.jsonl` | 355 | `2fa6eaf2…96c48a17` | Checkpoint selection (validation) |
| `data/splits/kev_domain/overfit32.v2.jsonl` | 32 | `fafb70cc…72eaee` | Smoke runs only |
| `data/splits/kev_domain/dev_human.v1.jsonl` | about 200 | after the freeze | Test set: scored once |

The domain files are derived from routing data v2 (`data/splits/kev/*.v2.jsonl`, tracked) by
`python scripts/build_domain_phase1.py --version v2 --laya`. Full hashes are in
`data/MANIFEST.md` and `configs/train.yaml`; `python -m analyst.models.kev_runs check-data`
compares the local files with them.

**Coverage** (`python -m analyst.models.kev_report coverage`; output
`outputs/reports/kev_data_coverage_v2.{json,md}`):

- Every one of the 14 catalogue tables appears in every split, both as a table named by a
  template and as the top-ranked catalogue candidate. In train, a table is named by between 19
  (`mandi_daily_prices`) and 244 (`plfs_state_ur_usual_status`) records, and ranked first in
  between 27 and 498 records.
- All eight domain labels are present in every split. In train, the shares range from 5.0%
  (`multiple`) to 31.8% (`labour`).
- Skew, reported and not corrected: the two tables of the first generator (PLFS unemployment, IMD
  subdivision rainfall) account for most of the template-named records, and `labour` and
  `rainfall` together make up 57% of the train labels. No class weighting is applied; per-label
  F1 is reported so that minority labels stay visible.
- Census 2011 is not in the published catalogue and is therefore not covered.
- Label sources in train: rules 1,287, paraphrases 324, teacher 265.

**State length** (`scripts/kev_state_lengths.py`, run in the Kev environment; output
`outputs/reports/kev_state_lengths_v2.json`): the median state is 248 Qwen tokens and the
maximum is 318, below `--max_state 384`. No training record is dropped by `kev.train`, and none
is truncated at serving.

## 2. Fixed settings (Kev commit `2074cc44`)

| Setting | Value | Source |
| --- | --- | --- |
| Base model | `Qwen/Qwen3.5-0.8B-Base` at `dc7cdfe2` | `configs/train.yaml` |
| Warm start | `jaredpalmer/kev-0.8b@bf75a6a8…` (LoRA rank 16, pointer head 256); the revision is part of the `--init_from` value, because `kev.train` has no revision flag and a bare Hub id resolves to the current `main` | `configs/train.yaml`; `kev/checkpoint.py:38-45` |
| Adapter | LoRA rank 16, alpha 32 (2 x rank), dropout 0.05, all linear modules | `kev/model.py:274` |
| Loss | Cross-entropy over the options' pointer logits; no label smoothing, Brier or focal term | `kev/train.py:41-61`, `:384` |
| Optimizer | AdamW, weight decay 0.01 on LoRA and head parameters | `kev/train.py:377`, `:580` |
| Schedule | OneCycle, 10% warm-up, over all optimizer steps | `kev/train.py:588` |
| Gradient clipping | Global norm 1.0; clipped steps reported per epoch | `kev/train.py:632` |
| Batch | 1 record per forward pass, gradient accumulation 8 (effective batch 8) | `configs/train.yaml` |
| Augmentation (on the fly, per record and epoch) | Option order always shuffled; a 'none' option added as a wrong alternative with probability 0.12, an unrelated option with 0.15; label replacement by 'none of the above' switched off (`--p_none 0`). The data files are not changed | `kev/data.py:320-343`, `kev/train.py:400-402`, `configs/train.yaml` |
| Precision | fp32 weights and compute; no mixed precision (the T4 has no bf16, and `kev.train` has no fp16) | `kev.train --help` |
| Validation during training | None for LoRA runs; validation loss is measured on the saved checkpoint | `kev.train --help` |

## 3. Runs

Planned (8 of the 13 one-factor runs in `configs/train.yaml`):

| Run | Varies | Platform | Priority |
| --- | --- | --- | --- |
| `b0_s0` | B0: lr 2e-5, 2 epochs, warm start, seed 0 | Kaggle session 1 | 1 |
| `lr1e-05`, `lr4e-05` | Learning rate | Kaggle sessions 1 and 2 | 2 |
| `b0_s1`, `b0_s2` | Seed (noise floor) | Kaggle sessions 2 and 3 | 3 |
| `ep3`, `ep1` | Training horizon (3 and 1 epochs) | Kaggle session 3 | 4 |
| `base_r16` | Start from the base model, lr 2e-4 (fresh adapter and head) | Colab session 1 | 5 |

Sessions (`configs/train.yaml`, `sessions`; one list per GPU, run in order): `kaggle_1`
(`b0_s0` | `lr1e-05`), `kaggle_2` (`lr4e-05` | `b0_s1`), `kaggle_3` (`ep3` | `b0_s2`, then
`ep1`), `colab_1` (`base_r16`). Every Kev run trains on a CUDA T4, so no comparison mixes training
devices. Deferred, run only if compute remains: `n250`, `n500`, `n1000` (training-set size) and
`base_r8`, `base_r32` (LoRA rank from the base model). Accuracy and ECE for every run are measured
on one backend (the local machine).

`ep1`, B0 and `ep3` are separate runs, each with a OneCycle schedule over its own length. They
compare training horizons; they are not checkpoints of one run, so they are not reported as early
stopping. `base_r16` differs from B0 in two settings (start point and learning rate) because a
fresh adapter and head at the warm-start rate would under-train and overstate the warm start.

## 4. Procedure

1. **Smoke run, once per platform**: notebook `notebooks/kev_train_t4.ipynb` with `SMOKE = True`
   (one run per GPU, so Kaggle tests the two-process launch), or `scripts/run_kev_local.py smoke`
   locally. The smoke run has 16 optimizer steps (accumulation 2), so at least one loss line is
   printed. Pass criteria: exit code 0, a loss line in `train.log`, the adapter, its configuration,
   the head and `training_metrics.json` written. The notebook checks before any download that
   PyTorch can use CUDA on every GPU it needs, that scratch space suffices and that the Kev clone
   is clean.
2. **Kaggle**: `PLATFORM = "kaggle"`, `SMOKE = False`, `SESSION = "kaggle_1"` (then `kaggle_2`,
   `kaggle_3`), then "Save Version" with "Save & Run All".
3. **Colab**: `PLATFORM = "colab"`, `SMOKE = False`, `SESSION = "colab_1"`; keep the tab open.
4. **Saving**: each run is validated and saved as soon as its process exits; a failed run is saved
   as `<run id>.failed-<time>` and never overwrites a finished run. Live logs are kept in
   `checkpoints/_logs/` on persistent storage.
5. **Collect**: each run folder goes to `models/checkpoints/<run id>/` (Kaggle output or Drive
   `Group4/checkpoints/<run id>/`). Weights stay out of git.
6. **Score** (local machine): `scripts/score_kev_run.sh <run id>`, which writes
   `outputs/reports/score_domain_<run id>.json`. Zero-shot reference:
   `scripts/score_kev_run.sh zeroshot_v2 released`.
7. **Register**: `.venv/bin/python -m analyst.models.kev_runs register models/checkpoints/<run id>
   --run-id <run id> --drive-path Group4/checkpoints/<run id> --scores
   outputs/reports/score_domain_<run id>.json`. This updates `models/registry.json` and copies the
   record files to `outputs/reports/kev_runs/<run id>/`.
8. **Records**: `python -m analyst.models.kev_report table`, `curves`, then `select`.

## 5. Selection rule (fixed before any dev_human score)

1. The temperature of each run is fitted on `calibration` (NLL).
2. The checkpoint is selected on `dev_synthetic` NLL after that temperature; macro-F1 breaks ties.
3. Only the planned runs compete (no zero-shot, smoke or older registered run). A setting other
   than B0 is selected only if its NLL is below the mean NLL of the three B0 seeds by more than
   their range (max - min). Otherwise the B0 seed with the lowest NLL is selected. This is a
   conservative range heuristic, not a significance test, and is reported as such.
4. `dev_human` is the test set. It is scored once, after the freeze, for the selected checkpoint
   and the reference rows. It is never used to choose, tune or recalibrate.

The rule is implemented in `analyst.models.kev_report.select`, and its output is
`outputs/reports/kev_selection.json`.

## 6. Evaluation on dev_human (after the freeze, Thursday 19 November)

```bash
python scripts/label_agreement.py freeze --items data/labels/dev_human_v1/items_rendered.jsonl
python scripts/build_domain_phase1.py --dev-human data/splits/kev/dev_human.v1.jsonl
SPLITS=dev_human scripts/score_kev_run.sh <selected run>
SPLITS=dev_human scripts/score_kev_run.sh zeroshot_v2 released
# Jev (spend approved separately): same records, TypeSafe endpoint
.venv/bin/python -m analyst.evaluation.decision_eval run --decision domain \
  --file data/splits/kev_domain/dev_human.v1.jsonl --base-url https://api.typesafe.ai \
  --model jev-latest --api-key-env TYPESAFE_API_KEY --out outputs/predictions/domain_jev_dev_human.jsonl
# gate and cascade: Kev temperature from its calibration predictions
.venv/bin/python -m analyst.evaluation.decision_eval gate --decision domain \
  --kev-calibration outputs/predictions/domain_<selected>_calibration.jsonl \
  --kev-dev outputs/predictions/domain_<selected>_dev_human.jsonl \
  --jev-dev outputs/predictions/domain_jev_dev_human.jsonl --out outputs/reports/gate_domain.json
.venv/bin/python -m analyst.evaluation.decision_eval cascade --decision domain \
  --kev-calibration outputs/predictions/domain_<selected>_calibration.jsonl \
  --kev-dev outputs/predictions/domain_<selected>_dev_human.jsonl \
  --jev-dev outputs/predictions/domain_jev_dev_human.jsonl --out outputs/reports/cascade_domain.json
```

Gate (`configs/inference.yaml`, `gate`): Kev accuracy within 3 points of Jev, and ECE at most
0.10 after temperature scaling. The point estimate decides (`decides: point_estimate`, fixed
before dev_human); the non-inferiority result (lower 95% bound) is reported beside it. The cascade
threshold needs at least 30 accepted calibration items and reports the one-sided 95% upper bound
of their error rate; a cost that is not reported by a backend is shown as unknown, not as zero.
Prediction files must cover identical item sets (no silent subsets), and every probability row
must give exactly the eight options. Option-order robustness: the selected checkpoint is scored
with three option orders (`decision_eval run --option-order-seed 1` and `2`, then `flips`);
inference only. The Laya row follows `docs/specs/laya_feasibility_plan.md`.

## 7. Records for the Milestone 4 report

| Report heading | Evidence |
| --- | --- |
| 2 Training dataset | Section 1; `kev_data_coverage_v2.md`; `kev_state_lengths_v2.json`; `data/MANIFEST.md` |
| 3 Model configuration | Section 2; `base_r16` against B0 (pretrained against base start) |
| 4 Training environment | `outputs/reports/kev_runs/<run>/environment.json` (platform, GPU, Python, torch, CUDA, transformers, peft); `pip_freeze.txt` on Drive |
| 5 Training methodology | Sections 2 and 4 |
| 6 Hyperparameter experiments | `kev_runs_table.md` (learning rate, epochs, seed, start point); batch size and scheduler not varied (Section 8) |
| 7 Optimization methods | Section 2; clipped-step share per run in `kev_runs_table.md`; training-horizon runs `ep1`, B0 and `ep3` (no true early stopping for LoRA runs) |
| 8 Regularization | LoRA dropout 0.05, weight decay 0.01, low-rank adapter, paraphrase augmentation (324 records), on-the-fly option shuffling and added options (Section 2); no label smoothing or class weights; seeds instead of cross-validation |
| 9 Training progress | `outputs/figures/kev_train_loss.png` and `kev_train_loss.csv`; `kev_validation_by_epoch.json` and `.png` |
| 10 Model selection | Section 5; `kev_selection.json` |
| 11 Challenges | Section 8 |
| 12 Summary | The selected run's row; `gate_domain.json`, `cascade_domain.json` |

## 8. Challenges log

| Date | Issue | Handling |
| --- | --- | --- |
| 12 Nov | `kev.train` offers fp32 and bf16 only, and the T4 has no bf16 | Every run is fp32; no mixed precision |
| 12 Nov | Under `--init_from`, the LoRA rank must equal the released rank (16) | Rank runs start from the base model and are deferred |
| 17 Nov | LoRA runs cannot resume after a session ends | Runs of about one hour; a failed run is restarted; Kaggle runs unattended |
| 17 Nov | No validation loss during LoRA training | Validation NLL is measured on each saved checkpoint; epochs 1, 2 and 3 give the curve |
| 17 Nov | The domain-only v2 files were not tracked and were missing from the working copy | Builder made version-aware; files rebuilt and matched byte for byte against the earlier copies |
| 17 Nov | Class skew (`labour` 31.8%, `multiple` 5.0% of train) | Reported with per-label F1; not reweighted |
| 17 Nov | Compute limits: one free account per platform per person | 8 of 13 runs planned; the rest are deferred |
| 17 Nov | Local smoke run: `kev.train` refuses an existing `--out` folder, which the local runner had created for its log | Runner fixed: the log is written beside the folder and moved in; an existing run folder is never overwritten |
| 17 Nov | Local smoke run (32 records, 4 updates): every update clipped (gradient norm about 18 against 1.0); about 17 s per update on MPS | Clipped-step share reported per run; `ep1` projected at about 67 min (estimate) |
| 17 Nov | Laya smoke run ran out of MPS memory in its own pre-training evaluation | Laya runs without `--eval` and with micro-batch 2 x accumulation 32 (same effective batch); see `docs/specs/laya_feasibility_plan.md` |
| M3 | 30 of 32 optimizer steps clipped in the 250-record local run | Clipped-step share is reported per run; lr 1e-5 tests whether it falls |
| 17 Nov | External code review (two independent reviewers) | Section 9 |

## 9. Changes after the external code review (17 November)

Each finding was checked against the Kev source (commit `2074cc44`) and the code before any change.

| Finding | Check | Change |
| --- | --- | --- |
| `--init_from` without a revision resolves to the current `main` | Confirmed (`kev/checkpoint.py:38-45`) | Warm start passed as `repo@revision`; the resolved snapshot is recorded (`init_source`) |
| Augmentation defaults (0.1/0.12/0.15) apply to our records | Confirmed (`kev/train.py:296`, `kev/data.py:320`) | Set explicitly; label replacement switched off (Section 2) |
| The from-base run trains a fresh head at the warm-start rate | Confirmed (`--head_lr` help) | `base_r16` at lr 2e-4 |
| `ep1` on MPS mixes the device into the epoch comparison | Valid | `ep1` moved to Kaggle session 3 |
| Epoch runs are not early stopping | Valid (OneCycle over each run's length) | Described as training-horizon runs |
| The smoke run printed no loss line (4 steps; printed every 10) | Confirmed in the local smoke run | Smoke accumulation 2 (16 steps) |
| Local runner pre-created the output folder | Confirmed in the local smoke run | Fixed; failed runs saved apart |
| Cloud runs saved only after all runs finished; failed runs could merge with old files | Valid | Per-run validation and saving; finished runs never overwritten |
| No PyTorch CUDA check before downloads; two-GPU path untested by the smoke run | Valid | CUDA and device-count check; one smoke run per GPU |
| `check-data` passed missing files; scores did not record input hashes | Valid | Missing fails; hashes in score files and per-prediction provenance files |
| Selection could pick an unplanned run | Valid | Only planned runs compete |
| Comparisons used the intersection of item ids; malformed probabilities were repaired | Valid | Identical id sets required; malformed rows rejected |
| Cascade threshold could rest on one item; missing cost shown as zero | Valid | At least 30 accepted items and an upper bound; unknown cost reported as unknown |
| Gate did not state which rule decides | Valid | `decides: point_estimate` in `configs/inference.yaml` |
| `pip_freeze.txt` not archived; dropped records not counted | Valid | Archived; dropped records parsed from the log |
| `--shared_prefix 1` could save compute | Not applicable: it shares the state across questions of a record, and phase-1 records have one question | No change |
| Temperature fitting might take the log of zero | Not a problem: probabilities are clipped at 1e-12 (`domain_eval.py:72,80`) | No change |
| Empty argument list under `set -u` in the scoring script (found while fixing) | Confirmed for the shell on the local machine | Fixed |

