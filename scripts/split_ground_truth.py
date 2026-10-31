"""Split the text-to-SQL ground truth into dev and test sets by template.

A template is a (dataset, category) pair. Every question of a template goes to
the same split, so no question pattern is seen in both. Groups are assigned in
a seeded random order until dev holds about 60% of the questions. Run from any
directory:

    python scripts/split_ground_truth.py
"""

from __future__ import annotations

import random
import re
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
GT_DIR = ROOT_DIR / "data" / "ground_truths"
SOURCE = GT_DIR / "text_to_sql_ground_truth_100.csv"
SEED = 29
DEV_SHARE = 0.6
NEAR_DUPLICATE_JACCARD = 0.8


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


gold = pd.read_csv(SOURCE)
gold["template"] = gold["dataset"] + "|" + gold["category"]

templates = sorted(gold["template"].unique())
random.Random(SEED).shuffle(templates)

# Abstain and clarify templates are split separately so both sets contain some.
non_answer = [
    t for t in templates if (gold.loc[gold["template"] == t, "expected_action"] != "answer").any()
]
answer = [t for t in templates if t not in non_answer]

dev_templates: set[str] = set(non_answer[::2])
target = DEV_SHARE * len(gold)
for template in answer:
    if gold["template"].isin(dev_templates).sum() < target:
        dev_templates.add(template)

gold["split"] = gold["template"].map(lambda t: "dev" if t in dev_templates else "test")
dev = gold[gold["split"] == "dev"].drop(columns=["template", "split"])
test = gold[gold["split"] == "test"].drop(columns=["template", "split"])

# Leakage checks: shared ids, shared templates, near-duplicate question text.
assert not set(dev["id"]) & set(test["id"])
assert not set(gold.loc[gold["split"] == "dev", "template"]) & set(
    gold.loc[gold["split"] == "test", "template"]
)
near = [
    (a, b)
    for a, qa in zip(dev["id"], dev["question"])
    for b, qb in zip(test["id"], test["question"])
    if len(words(qa) & words(qb)) / len(words(qa) | words(qb)) >= NEAR_DUPLICATE_JACCARD
]

dev.to_csv(GT_DIR / "text_to_sql_dev.v1.csv", index=False)
test.to_csv(GT_DIR / "text_to_sql_test.v1.csv", index=False)

for name, part in [("dev", dev), ("test", test)]:
    print(
        f"{name}: {len(part)} questions; "
        + ", ".join(f"{k} {v}" for k, v in part["dataset"].value_counts().items())
        + "; actions "
        + ", ".join(f"{k} {v}" for k, v in part["expected_action"].value_counts().items())
    )
print(f"templates: dev {len(dev_templates)}, test {len(templates) - len(dev_templates)}")
print(
    f"near-duplicate dev/test question pairs (word Jaccard >= {NEAR_DUPLICATE_JACCARD}): {len(near)}"
)
for pair in near:
    print("  ", pair)
