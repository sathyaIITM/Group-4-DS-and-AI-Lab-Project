"""Phase 1 of the Kev adoption: the domain decision alone.

Phase 1 takes Kev-0.8B through training, calibration, serving and evaluation on one decision
(domain) before tool selection moves to it (phase 2, a joint retrain). A phase-1 record is a
routing record that keeps the state and the `domain` question and drops the `tool` question.
The question text is the canonical text of `kev_questions`, so training and serving requests
stay identical.
"""

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from analyst.decisions.kev_questions import DOMAIN_INSTRUCTIONS, DOMAIN_OPTIONS, QUESTIONS

PHASE = 1
SPLITS = ("train", "calibration", "dev_synthetic")


def domain_question() -> dict[str, Any]:
    """The `domain` entry of a /v1/systemone request, without a label."""
    return {"type": "choice", "instructions": DOMAIN_INSTRUCTIONS, "criteria": DOMAIN_OPTIONS}


def to_domain_record(record: dict[str, Any]) -> dict[str, Any]:
    """Keep the state and the domain question and label; drop the tool question."""
    question = record["questions"]["domain"]
    instructions, criteria = QUESTIONS["domain"]
    if question["instructions"] != instructions or question["criteria"] != criteria:
        msg = f"domain question of {record['_meta']['id']} differs from the canonical text"
        raise ValueError(msg)
    if question["label"] not in criteria:
        msg = f"label {question['label']!r} of {record['_meta']['id']} is not an option"
        raise ValueError(msg)
    meta = dict(record["_meta"])
    meta["phase"] = PHASE
    return {"state": record["state"], "questions": {"domain": question}, "_meta": meta}


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield the JSON objects of a JSONL file."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def convert_split(source: Path, target: Path) -> int:
    """Convert one routing split file; return the number of records written."""
    records = [to_domain_record(r) for r in read_jsonl(source)]
    write_jsonl(target, records)
    return len(records)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    """Write JSON objects to a JSONL file, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def subsample(records: list[dict[str, Any]], n: int, seed: int = 0) -> list[dict[str, Any]]:
    """A reproducible sample that keeps the order of the source file and covers every label."""
    import random

    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not security
    by_label: dict[str, list[int]] = {}
    for index, record in enumerate(records):
        by_label.setdefault(record["questions"]["domain"]["label"], []).append(index)
    chosen: set[int] = set()
    for indices in by_label.values():  # at least one record per label
        chosen.add(rng.choice(indices))
    remaining = [i for i in range(len(records)) if i not in chosen]
    rng.shuffle(remaining)
    chosen.update(remaining[: max(0, n - len(chosen))])
    return [records[i] for i in sorted(chosen)]


def to_laya_row(record: dict[str, Any], decision: str = "domain") -> dict[str, Any]:
    """A Kev record as a Laya training row (`{state, questions, expected}`; laya 0.4.23,
    `laya.train.rows_to_items`): the same state and question text, the label moved to
    `expected`, so both models are fine-tuned on identical inputs."""
    question = dict(record["questions"][decision])
    label = question.pop("label")
    question.setdefault("type", "choice")
    return {
        "state": record["state"],
        "questions": {decision: question},
        "expected": {decision: label},
        "_meta": {"id": record["_meta"]["id"]},
    }


def dev_human_record(row: dict[str, Any]) -> dict[str, Any]:
    """A frozen dev_human row (`{id, state, tool, domain, label_source}`, written by
    `scripts/label_agreement.py freeze`) as a Kev record with both routing questions in their
    canonical text, so every backend is scored on identical requests."""
    questions = {}
    for decision in ("tool", "domain"):
        instructions, criteria = QUESTIONS[decision]
        if row[decision] not in criteria:
            raise ValueError(f"{row['id']}: {decision} label {row[decision]!r} is not an option")
        questions[decision] = {
            "type": "choice",
            "instructions": instructions,
            "criteria": criteria,
            "label": row[decision],
        }
    meta = {"id": row["id"], "label_source": row.get("label_source", "human"), "split": "dev_human"}
    return {"state": row["state"], "questions": questions, "_meta": meta}
