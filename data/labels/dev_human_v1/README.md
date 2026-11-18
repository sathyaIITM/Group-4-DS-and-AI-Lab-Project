# dev_human v1: human-labelled routing set

Purpose: model selection and the adoption gate for the routing decisions (tool selection and
domain). The labels of this set are written by hand by T1, T2 and T4; they are never used for
training, and no tuning against this set is allowed after the freeze.

## Contents

| File | Content |
| --- | --- |
| `items.jsonl` | 200 items prepared by T3: `{"id", "message", "context": {"has_result", "prior_turn", "previous_tool"}}` |
| `overlap_check.json` | Near-duplicate check against the training splits, the candidate files and the sample question sets (character 5-gram Jaccard at least 0.8): no item flagged |
| `labels_<T#>.csv` | One file per labeller: `item_id,tool,domain,rule,undecided,note` |
| `disagreements_<T#>.csv` | Written by `scripts/label_agreement.py agree` for each adjudicator |

## Quotas

| Tool | Items |
| --- | --- |
| `run_sql` | 60 |
| `ask_clarification` | 32 |
| `decline_not_covered` | 28 |
| `search_catalog` | 20 |
| `describe_table` | 20 |
| `make_chart` (with a result) | 20 |
| `explain_result` (with a result) | 20 |

Domains: at least 20 items each for `labour`, `agriculture`, `rainfall`, `prices_economy` and
`health`; at least 16 for `other`, 12 for `multiple` and 12 for `unspecified`.

## Labelling protocol

- Guide: `docs/specs/labelling_guide_v1.md`, version 1.0. Judge each item as if the router
  shows the table the message is about among its top-4 catalogue candidates, unless the
  message names a topic that no published table covers.
- Blocks: A (dh-001 to dh-067) labelled by T1 and T2, adjudicated by T4; B (dh-068 to dh-134)
  by T2 and T4, adjudicated by T1; C (dh-135 to dh-200) by T4 and T1, adjudicated by T2.
- Labels are decided by hand, from the item and the guide only. No assistant tool, model,
  script or search result is used to choose or suggest a label. Items are not discussed with
  the other labeller or with T3 before adjudication.
- Record the deciding rule. When no rule decides, set `undecided=true`.
- Agreement: `python scripts/label_agreement.py agree` (Cohen's kappa per decision and block;
  target 0.80). Freeze: `python scripts/label_agreement.py freeze --items <rendered items>`.

## Format corrections

`labels_T2.csv` (submitted 2026-11-18 as commit 0589eba) was corrected for format only, so that
`label_agreement.py` can read it; no label was re-decided:

- header set to `item_id,tool,domain,rule,undecided,note` (was `Item_ID,...,rule ,...`), byte-order
  mark and trailing spaces removed, `TRUE`/`FALSE` written as `true`/`false`;
- `economy` written as the option name `prices_economy` (16 items: dh-002, 006, 008, 016, 028,
  044, 053, 060, 075, 077, 080, 082, 089, 093, 125, 127);
- `missing`, which is not an option, replaced by the label of the domain rule the labeller cited
  in `note`: M8 `unspecified` (dh-067, 081, 085, 087, 101, 103, 113) and M5 `other` (dh-110).
  To be confirmed by T2.

T3's intended labels are sealed outside the repository; their SHA-256 is posted to the team
before labelling starts and they are compared with the final labels only after the freeze.
