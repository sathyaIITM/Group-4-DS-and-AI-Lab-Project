# stress_v1: hard cases for the domain decision

Version 1.0, 25 November 2026. Purpose: to check how the calibration of the domain decision and
the cascade to Jev behave on messages that are ambiguous, unfamiliar or written in an unusual way
(Milestone 4 review, point 6). It is an evaluation set: never used for training, tuning, the
temperature fit or the choice of the cascade threshold.

## Contents

| File | Content |
| --- | --- |
| `items.jsonl` | 80 messages written by T3: `{"id", "message", "context"}` (no earlier result) |
| `items_rendered.jsonl` | The router state of each item (top-4 catalogue lines, context, message), built by `scripts/render_dev_human.py`, as at serving time; SHA-256 in `items_rendered.sha256` |
| `overlap_check.json` | Near-duplicate check (character 5-gram Jaccard at least 0.8) against routing data v2, `e2e_v1`, `e2e_dev_extra` and `dev_human`: no item flagged |
| `labels_T1.csv`, `labels_T2.csv` | One file per labeller: `item_id,tool,domain,rule,undecided,note` |

The mix (written to the plan in the T3 checklist, R8): measures from two domains on equal terms,
messages that name no measure, topics outside the five domains and non-data messages,
paraphrases of covered measures, Hindi and Hinglish, typos and abbreviations, and measures named
by their source or not in the catalogue. T3's intended labels are sealed outside the repository
(SHA-256 `2e5bd9cb272fde59e3e2f2f70d7b6d2a2e16cbca7910ab4b75f7b31352e11c8a`) and are used only as
a diagnostic, as for `dev_human`.

## Labelling protocol

- Label the **domain** only (leave `tool` empty), with the domain rules of
  `docs/specs/labelling_guide_v1.md`, Section 3 (M1-M8, domain scope and the two boundary rules).
  Record the rule in `rule` (for example `M1`, `M7`).
- The domain is the domain of the measure asked for, whether or not a table covers it (M1). A
  measure outside the five domains, or a message that is not a data request, is `other`
  (M5, M6); two measures on equal terms is `multiple` (M7); no nameable measure is `unspecified`
  (M8).
- Decide by hand, from the item and the guide only. No assistant tool, model, script or search
  is used to choose or suggest a label. Do not discuss items with the other labeller before both
  files are in.
- An item no rule decides: `undecided` = `TRUE` and a one-line note.
- Due: Wednesday 25 November, 16:00. T3 runs `scripts/label_agreement.py` and adjudicates
  disagreements.
