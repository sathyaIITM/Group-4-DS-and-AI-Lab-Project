"""The `dev_human` routing set: overlap check, label agreement, adjudication and freeze.

Protocol: T3 brief Section 6 (`docs/handoff/milestone-4`, outside the repository) and
`02_Labelling_and_Model_Evaluation.md`. T3 prepares the 200 items; T1, T2 and T4 label them by
hand in three blocks, two labellers per block and the third member adjudicating.

Files (all under `data/labels/dev_human_v1/`):

- `items.jsonl`: `{"id": "dh-001", "message": ..., "context": {"has_result": ..., ...}}`
- `labels_<T#>.csv`: `item_id,tool,domain,rule,undecided,note`, one file per labeller
- `disagreements_<T#>.csv`: written for each adjudicator; the adjudicator fills `final_label`
  and `final_rule`, or sets `ambiguous` to true
"""

import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sklearn.metrics import cohen_kappa_score

from analyst.data.kev_checks import SHINGLE, shingles
from analyst.decisions.kev_questions import QUESTIONS

DECISIONS = ("tool", "domain")
KAPPA_TARGET = 0.80
OVERLAP_THRESHOLD = 0.8
LABEL_COLUMNS = ("item_id", "tool", "domain", "rule", "undecided", "note")
DISAGREEMENT_COLUMNS = (
    "item_id",
    "decision",
    "labeller_a",
    "label_a",
    "rule_a",
    "labeller_b",
    "label_b",
    "rule_b",
    "final_label",
    "final_rule",
    "ambiguous",
    "note",
)


@dataclass(frozen=True)
class Block:
    """A block of dev-human items with its labellers and adjudicator."""

    name: str
    first: int
    last: int
    labellers: tuple[str, str]
    adjudicator: str

    def holds(self, item_id: str) -> bool:
        """Return True when an item belongs to the block."""
        return self.first <= item_number(item_id) <= self.last


BLOCKS = (
    Block("A", 1, 67, ("T1", "T2"), "T4"),
    Block("B", 68, 134, ("T2", "T4"), "T1"),
    Block("C", 135, 200, ("T4", "T1"), "T2"),
)


def item_number(item_id: str) -> int:
    """Return the number of a dh-NNN item id."""
    prefix, _, number = item_id.partition("-")
    if prefix != "dh" or not number.isdigit():
        raise ValueError(f"item id {item_id!r} is not of the form dh-NNN")
    return int(number)


def block_of(item_id: str) -> Block:
    """Return the block an item belongs to."""
    for block in BLOCKS:
        if block.holds(item_id):
            return block
    raise ValueError(f"{item_id} is in no block")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load the JSON objects of a JSONL file."""
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


# ---------------------------------------------------------------------------- overlap


def overlap(
    items: list[dict[str, Any]],
    references: dict[str, list[str]],
    threshold: float = OVERLAP_THRESHOLD,
) -> dict[str, Any]:
    """Flag items whose message is close to a reference message (character 5-gram Jaccard
    at or above `threshold`, after the same normalisation as the training-data checks).

    `references` maps a source name (a training split, `e2e_v1`) to its messages."""
    index: dict[str, set[int]] = defaultdict(set)
    texts: list[tuple[str, str, frozenset[str]]] = []
    for source, messages in references.items():
        for message in messages:
            grams = shingles(message)
            for gram in grams:
                index[gram].add(len(texts))
            texts.append((source, message, grams))
    flagged = []
    for item in items:
        grams = shingles(item["message"])
        candidates: set[int] = set()
        for gram in grams:
            candidates |= index.get(gram, set())
        best: tuple[float, int] | None = None
        for k in candidates:
            other = texts[k][2]
            jaccard = len(grams & other) / len(grams | other)
            if best is None or jaccard > best[0]:
                best = (jaccard, k)
        if best is not None and best[0] >= threshold:
            source, message, _ = texts[best[1]]
            flagged.append(
                {
                    "id": item["id"],
                    "message": item["message"],
                    "closest": message,
                    "source": source,
                    "jaccard": round(best[0], 3),
                }
            )
    return {
        "method": f"character {SHINGLE}-gram Jaccard after normalisation (kev_checks.normalise)",
        "threshold": threshold,
        "items": len(items),
        "reference_messages": {s: len(m) for s, m in references.items()},
        "flagged": flagged,
    }


def messages_of(path: Path) -> list[str]:
    """Messages from a Kev record file (`state.user_message`) or a question file
    (`question` or `message`)."""
    out = []
    for row in read_jsonl(path):
        state = row.get("state")
        if isinstance(state, dict) and "user_message" in state:
            out.append(str(state["user_message"]))
        elif "question" in row:
            out.append(str(row["question"]))
        elif "message" in row:
            out.append(str(row["message"]))
    return out


# ---------------------------------------------------------------------------- labels


def _truthy(value: str | None) -> bool:
    """Return True for yes-like text such as true, 1 or yes."""
    return (value or "").strip().lower() in {"true", "1", "yes", "y"}


def read_labels(path: Path) -> dict[str, dict[str, Any]]:
    """One labeller's file, validated against the question options."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != LABEL_COLUMNS:
            raise ValueError(f"{path.name}: columns must be {','.join(LABEL_COLUMNS)}")
        rows: dict[str, dict[str, Any]] = {}
        for line, row in enumerate(reader, start=2):
            item_id = row["item_id"].strip()
            item_number(item_id)
            if item_id in rows:
                raise ValueError(f"{path.name}:{line}: {item_id} labelled twice")
            undecided = _truthy(row["undecided"])
            for decision in DECISIONS:
                value = row[decision].strip()
                if not undecided and value not in QUESTIONS[decision][1]:
                    raise ValueError(f"{path.name}:{line}: {decision} {value!r} is not an option")
            rows[item_id] = {
                "tool": row["tool"].strip(),
                "domain": row["domain"].strip(),
                "rule": row["rule"].strip(),
                "undecided": undecided,
                "note": row["note"],
            }
    return rows


def agreement(labels: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Cohen's kappa per decision and per block, over items both labellers decided.

    `labels` maps a member (`T1`) to the output of `read_labels`."""
    result: dict[str, Any] = {"target": KAPPA_TARGET, "blocks": {}, "overall": {}}
    pooled: dict[str, tuple[list[str], list[str]]] = {d: ([], []) for d in DECISIONS}
    for block in BLOCKS:
        a_name, b_name = block.labellers
        labels_a, labels_b = labels.get(a_name, {}), labels.get(b_name, {})
        ids = sorted(i for i in set(labels_a) & set(labels_b) if block.holds(i))
        decided = [i for i in ids if not labels_a[i]["undecided"] and not labels_b[i]["undecided"]]
        entry: dict[str, Any] = {
            "labellers": [a_name, b_name],
            "adjudicator": block.adjudicator,
            "items_labelled_by_both": len(ids),
            "undecided": len(ids) - len(decided),
        }
        for decision in DECISIONS:
            x = [labels_a[i][decision] for i in decided]
            y = [labels_b[i][decision] for i in decided]
            pooled[decision][0].extend(x)
            pooled[decision][1].extend(y)
            entry[decision] = _kappa(x, y)
        result["blocks"][block.name] = entry
    for decision in DECISIONS:
        result["overall"][decision] = _kappa(*pooled[decision])
    result["meets_target"] = all(
        (v["kappa"] or 0.0) >= KAPPA_TARGET for v in result["overall"].values()
    )
    return result


def _kappa(x: list[str], y: list[str]) -> dict[str, Any]:
    """Return agreement and Cohen's kappa between two label lists."""
    if not x:
        return {"n": 0, "agreement": None, "kappa": None}
    observed = sum(p == q for p, q in zip(x, y, strict=True)) / len(x)
    kappa = float(cohen_kappa_score(x, y)) if len(set(x) | set(y)) > 1 else 1.0
    return {"n": len(x), "agreement": round(observed, 4), "kappa": round(kappa, 4)}


def disagreements(labels: dict[str, dict[str, dict[str, Any]]]) -> dict[str, list[dict[str, str]]]:
    """Rows for each adjudicator: every (item, decision) where the two labels differ, or
    where either labeller marked the item undecided."""
    out: dict[str, list[dict[str, str]]] = {
        labelling_block.adjudicator: [] for labelling_block in BLOCKS
    }
    for block in BLOCKS:
        a_name, b_name = block.labellers
        labels_a, labels_b = labels.get(a_name, {}), labels.get(b_name, {})
        for item_id in sorted(set(labels_a) & set(labels_b), key=item_number):
            if not block.holds(item_id):
                continue
            undecided = labels_a[item_id]["undecided"] or labels_b[item_id]["undecided"]
            for decision in DECISIONS:
                if undecided or labels_a[item_id][decision] != labels_b[item_id][decision]:
                    out[block.adjudicator].append(
                        {
                            "item_id": item_id,
                            "decision": decision,
                            "labeller_a": a_name,
                            "label_a": labels_a[item_id][decision],
                            "rule_a": labels_a[item_id]["rule"],
                            "labeller_b": b_name,
                            "label_b": labels_b[item_id][decision],
                            "rule_b": labels_b[item_id]["rule"],
                            "final_label": "",
                            "final_rule": "",
                            "ambiguous": "",
                            "note": "",
                        }
                    )
    return out


def write_csv(path: Path, columns: Iterable[str], rows: list[dict[str, str]]) -> None:
    """Write rows to a CSV file with the given columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


def missing_items(
    labels: dict[str, dict[str, dict[str, Any]]], item_ids: list[str]
) -> dict[str, list[str]]:
    """Items each labeller still has to label in their two blocks."""
    out = {}
    for member in sorted({m for b in BLOCKS for m in b.labellers}):
        expected = [i for i in item_ids if member in block_of(i).labellers]
        out[member] = [i for i in expected if i not in labels.get(member, {})]
    return out


# ---------------------------------------------------------------------------- freeze


def final_labels(
    labels: dict[str, dict[str, dict[str, Any]]],
    adjudications: list[dict[str, str]],
    item_ids: list[str],
) -> tuple[dict[str, dict[str, str]], list[str], list[str]]:
    """Agreed labels plus adjudicated ones. Returns (final, ambiguous ids, unresolved ids)."""
    decided: dict[tuple[str, str], str] = {}
    ambiguous: set[str] = set()
    for row in adjudications:
        key = (row["item_id"], row["decision"])
        if _truthy(row.get("ambiguous")):
            ambiguous.add(row["item_id"])
        elif row.get("final_label", "").strip():
            value = row["final_label"].strip()
            if value not in QUESTIONS[row["decision"]][1]:
                raise ValueError(f"{key}: final label {value!r} is not an option")
            decided[key] = value
    final: dict[str, dict[str, str]] = {}
    unresolved: list[str] = []
    for item_id in item_ids:
        if item_id in ambiguous:
            continue
        a_name, b_name = block_of(item_id).labellers
        label_a, label_b = labels.get(a_name, {}).get(item_id), labels.get(b_name, {}).get(item_id)
        if label_a is None or label_b is None:
            unresolved.append(item_id)
            continue
        chosen = {}
        for decision in DECISIONS:
            agreed = (
                not label_a["undecided"]
                and not label_b["undecided"]
                and label_a[decision] == label_b[decision]
            )
            label = label_a[decision] if agreed else decided.get((item_id, decision))
            if label is None:
                break
            chosen[decision] = label
        if len(chosen) == len(DECISIONS):
            final[item_id] = chosen
        else:
            unresolved.append(item_id)
    return final, sorted(ambiguous, key=item_number), unresolved


def compare_intended(final: dict[str, dict[str, str]], intended: Path) -> dict[str, Any]:
    """Diagnostic after the freeze: how often the final labels differ from T3's sealed ones."""
    with intended.open(encoding="utf-8", newline="") as handle:
        sealed = {r["item_id"]: r for r in csv.DictReader(handle)}
    shared = [i for i in final if i in sealed]
    out: dict[str, Any] = {"n": len(shared), "sha256": sha256_file(intended)}
    for decision in DECISIONS:
        differ = [i for i in shared if sealed[i][decision].strip() != final[i][decision]]
        out[decision] = {"differ": len(differ), "share": len(differ) / max(len(shared), 1)}
        out[f"{decision}_items"] = differ
    return out
