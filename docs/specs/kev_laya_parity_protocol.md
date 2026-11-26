# Kev and Laya: matched fine-tuning protocol (Milestone 5)

Version 1.0, 24 November 2026. Owner: T3. Status: fixed before any run under it was started.
Supersedes, for Milestone 5, the comparator design of `laya_feasibility_plan.md` (single default
Laya run) and extends `kev_training_protocol.md` (Kev sweep, Milestone 4). This is the last
fine-tuning phase of the project: every run listed here is completed in Milestone 5, and no run is
added after results are seen.

## 1. Purpose

Compare Kev-0.8B and Laya on the two decisions of the router, domain and tool selection, with the
same data, the same augmentation, the same search procedure, the same number of seeds and the same
selection and evaluation rules, and choose a model for each decision by a rule fixed in advance.

## 2. Facts that shape the design (checked 24 November)

| Item | Finding | Source |
| --- | --- | --- |
| Kev learning rate | Default for a fine-tune from `kev-0.8b` is 4e-5 (the checkpoint's own training value), capped at 5e-5; the README suggests 2e-5 as a start | Kev `skills/kev-finetune/references/hill-climbing.md`; Kev README "By Hand" |
| Kev epochs | 2 epochs when there are 1,000+ records and the loss is still falling after epoch 1; over-confidence after fine-tuning usually means too many epochs | Kev hill-climbing guide |
| Kev augmentation | Per epoch: option order always permuted; with probability 0.12 a "none of the above" option added as a wrong alternative; with probability 0.15 an irrelevant distractor added (our `b0` settings; `p_none` 0) | `kev/data.py` `augment`, `kev/train.py` `record_variants` |
| Laya defaults | 4 epochs, encoder learning rate 2.5e-5, head learning rate 1e-4, micro-batch 8 x accumulation 8, RLCD loss | `laya-train --help`; Laya README |
| Laya hold-out | `laya-train` always holds out 10% of rows (`calib_frac` 0.1) for its own thresholds; the Python API accepts `calib_frac` 0 | `laya/train.py` (`TrainConfig`, `split_calibration`) |
| Laya question budget | Default `head_max_len` 192 tokens; the tool question needs 264 (7 option descriptions cut to 25 tokens each); the domain question needs 163 | Measured with `laya.train.build_head` |
| State lengths | Longest state 283 Laya tokens (limit 512); 318 Kev tokens (limit 384); no truncation in either model | Measured; `scripts/kev_state_lengths.py` |
| Probability precision | Both servers round probabilities to 4 decimals | `kev/api.py` `round_prob`; `laya/agent.py` |
| Encoder fine-tuning ranges | ModernBERT (Laya's encoder) GLUE sweep: learning rates 1e-5 to 8e-5, epochs 1 to 10 by task | Warner et al. 2024, arXiv:2412.13663 |
| Seed variance | Fine-tuning outcomes vary materially with the random seed (initialisation and data order) on small data; several seeds are needed before two settings are compared | Dodge et al. 2020, arXiv:2002.06305; Mosbach et al. 2021, arXiv:2006.04884 |

## 3. Parity rules

| # | Rule |
| --- | --- |
| P1 | Same rows: the domain cell trains on the 1,876 records of `data/splits/kev_domain/train.v2.jsonl`, the joint cell on the 3,752 single-question records of `data/splits/kev/phase2_split/train.v2.jsonl`. Laya keeps no internal hold-out (`calib_frac` 0). |
| P2 | Same augmentation: Laya trains on the exact variants `kev.train` draws for the same seed and epoch (`scripts/build_parity_data.py`, checked against `kev.train.record_variants`: 0 mismatches in 1,072 sampled variants). The E epoch variants are written in sequence and Laya trains one pass over them, so both models take the same number of item passes. |
| P3 | Same visible text: Laya `head_max_len` 320 for training and inference, so no option description is cut; no state is truncated in either model. |
| P4 | Same calibration: both models are served at temperature 1 (Laya's inherited temperatures removed in the served copy); one temperature per decision is fitted on `calibration.v2` by the same code (`decision_eval score`). |
| P5 | Same search: one-factor sweep around each model's default (learning rate x0.5 and x2 at the default epochs; epochs x0.5 and x1.5 at the default learning rate), the default with seeds 0, 1, 2, every other setting with seed 0. |
| P6 | Same seeds and same compute class: seeds 0, 1, 2; NVIDIA T4 for all training; wall time recorded per run. |
| P7 | Shared fixes only: no model-specific change to data, prompts or labels during this phase. |

## 4. Runs (fixed count)

| Step | Kev-0.8B | Laya |
| --- | --- | --- |
| Domain sweep (P5) | Done in Milestone 4: `b0_s0..s2` (lr 2e-5, 2 epochs), `lr1e-05`, `lr4e-05`, `ep1`, `ep3` | 7 runs: `laya_dom_def_s0..s2` (enc lr 2.5e-5, 4 epochs), `laya_dom_lr1.25e-05`, `laya_dom_lr5e-05`, `laya_dom_ep2`, `laya_dom_ep6` |
| Top-2 sweep settings by dev_synthetic NLL (Section 5), seeds 1 and 2 added | `ep3`, `lr4e-05` (already ranked first and second): 4 runs | Top 2 of its 4 non-default settings: 4 runs |
| Joint cell: the same two settings, seeds 0, 1, 2 | `joint_ep3_s0`, `_s1` done; `joint_ep3_s2`, `joint_lr4e-05_s0..s2`: 4 runs | 6 runs |
| Held-out table (`srs_imr_state`), joint, first-ranked setting, seed 0 | `heldout_joint_ep3_s0`: 1 run | 1 run |
| **New runs in this phase** | **9** | **18** |

`joint_ep3_s0` and `joint_ep3_s1` are the phase 2 runs (`configs/train.yaml` `phase2`, seeds and
selection fixed before any score and not changed here). They were trained and scored under the
phase 2 rule before this protocol was written; the parity phase reuses them as seeds 0 and 1 of
the `ep3` joint setting and adds `joint_ep3_s2` as a newly planned run under this protocol. The
phase 2 result is reported as such, beside the parity result.

The default setting is not a top-2 candidate in either model because it already has three seeds;
it competes in the cell selection of Section 5 with those three seeds. Kev's `base_r16`
(adapter trained from the base model) has no Laya counterpart (`laya-train` starts only from a
Laya checkpoint) and is reported as a Milestone 4 exploratory run.

Platforms: all runs on Kaggle (2 x T4, one queue per GPU). Laya in stages K1 and K3; Kev joint
and held-out runs in session `kaggle_5`; Kev domain seeds in session `kaggle_6` (first planned as
four one-run Colab sessions, 35 and 54 minutes measured; moved to Kaggle on 26 November with the
same settings and seeds). Laya starts from `convaiinnovations/laya` at revision
`fd4f9dbcf4fde222fd43174bdd4c3b08b789e4e1`; Kev from `jaredpalmer/kev-0.8b` at `bf75a6a8`.

## 5. Selection (synthetic data only)

| Choice | Rule |
| --- | --- |
| Top-2 sweep settings | Lowest dev_synthetic NLL after temperature (fitted on calibration), seed 0 |
| Setting of a cell | Lowest mean NLL over its 3 seeds on dev_synthetic (joint cell: mean of the domain and tool NLL); macro-F1 breaks ties |
| Served checkpoint of a cell | The seed of the chosen setting with the lowest NLL |

Laya sweep and seed runs are scored on the Kaggle GPU by the notebook (same questions, same
output format as `decision_eval run`); selection compares Laya runs only with Laya runs. The
served checkpoints of both models are then scored again on the local machine, the canonical
backend for every cross-model figure, with top-answer agreement against the Kaggle predictions
reported.

## 6. Evaluation and the choice of a model per decision

| Set | Use |
| --- | --- |
| `calibration.v2` | Temperatures and cascade thresholds only |
| `dev_synthetic.v2` | Selection (Section 5) |
| `dev_human` (domain v1; tool v1.1) | Gate and choice per decision; all three seeds of each chosen setting reported (mean and spread). Tool predictions of both models stay unopened until the tool re-adjudication (D17) is complete |
| `stress_v1` (domain) | Confirmation, frozen before scoring |
| End-to-end test runs (v4) | Confirmation of both decisions inside the agent |
| Held-out-table items | Generalisation (domain on all sets; tool after D17) |

Candidates: domain {Kev domain, Kev joint, Laya domain, Laya joint}; tool {Kev joint, Laya joint}.
Per decision: (1) gate: within 3 accuracy points of Jev on `dev_human` and ECE at most 0.10 after
temperature; (2) among candidates that pass, the most accurate is chosen only if an exact
McNemar test against the runner-up gives p < 0.05; (3) otherwise, in order: one checkpoint
serving both decisions, lower p95 latency on the local machine, lower peak memory. Each chosen
model escalates to Jev below a threshold set on calibration at a 5% error budget. Because the
choice among candidates uses `dev_human`, the unbiased figures are those of `stress_v1` and the
end-to-end test.

## 7. Schedule (IST)

| When | What |
| --- | --- |
| Tue 24 Nov, evening | Kaggle K1: Laya sweep (7 runs, about 70 min); Kev domain `lr4e-05_s1`, `_s2`, `ep3_s1`, `_s2` (moved to Kaggle `kaggle_6` on 26 November) |
| Tue 24 Nov, night | Kaggle K2: Kev joint and held-out (5 runs, about 4.5 h, unattended) |
| Wed 25 Nov, early | Laya sweep scored; top-2 settings fixed; Kaggle K3: Laya seeds, joint and held-out (11 runs, about 3 h) |
| Wed 25 Nov, day | Scoring; D17; tool scoring; choice per decision by 17:00 |
| Wed 25 Nov 18:00 to Thu 26 Nov 06:00 | Reserved for re-running a failed run with its identical configuration only |

## 8. Reporting

Every run in Section 4 with its setting, seed, platform, wall time and selection score; the three
seeds of each chosen setting; the final table on the canonical backend; what remained unequal
(the two starting checkpoints differ in what they were trained on; Kev's from-base run has no
Laya counterpart). `laya_s0` (library defaults, 10% hold-out, no augmentation) is reported as the
pre-parity reference row.

## References

- Dodge, J., Ilharco, G., Schwartz, R., Farhadi, A., Hajishirzi, H., Smith, N. (2020). Fine-Tuning
  Pretrained Language Models: Weight Initializations, Data Orders, and Early Stopping.
  arXiv:2002.06305.
- Mosbach, M., Andriushchenko, M., Klakow, D. (2021). On the Stability of Fine-tuning BERT:
  Misconceptions, Explanations, and Strong Baselines. ICLR 2021. arXiv:2006.04884.
- Warner, B. et al. (2024). Smarter, Better, Faster, Longer: A Modern Bidirectional Encoder for
  Fast, Memory Efficient, and Long Context Finetuning and Inference. arXiv:2412.13663.
- Kev repository (README, `skills/kev-finetune/references/hill-climbing.md`, `kev/data.py`,
  `kev/train.py`), commit `2074cc44`. https://github.com/jaredpalmer/kev
- Laya 0.4.23 package documentation and source (`laya/train.py`, `laya/agent.py`).
  https://pypi.org/project/laya/
