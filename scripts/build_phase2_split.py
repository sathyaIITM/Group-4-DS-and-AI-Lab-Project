"""Phase 2 training file: one single-question record per decision, from routing data v2.

    python scripts/build_phase2_split.py

Routing data v2 (`data/splits/kev/train.v2.jsonl`) carries both questions (tool and domain) on
every record. Trained in that form, kev.train holds both questions' branches in one step; on the
local machine the 32-record smoke run grew to about 18 GB and did not finish (24 November 2026),
which also puts the 16 GB T4 at risk. Splitting each record into two records with the same state,
one per question, trains one model on both decisions with the memory per step of the Milestone 4
domain runs. Labels, states and question text are unchanged; `_meta` gains `question` and
`source_index` (the line of the joint file).

Writes `data/splits/kev/phase2_split/train.v2.jsonl` and `overfit32.v2.jsonl` (the split of
`data/splits/kev/overfit32.v2.jsonl`) and prints their SHA-256 for `configs/train.yaml`.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "train.v2.jsonl": ROOT / "data/splits/kev/train.v2.jsonl",
    "overfit32.v2.jsonl": ROOT / "data/splits/kev/overfit32.v2.jsonl",
}
OUT = ROOT / "data/splits/kev/phase2_split"
QUESTIONS = ("tool", "domain")


def split_record(record: dict[str, Any], index: int) -> list[dict[str, Any]]:
    """Return one record per question, each with the same state."""
    rows = []
    for name in QUESTIONS:
        meta = {**record.get("_meta", {}), "question": name, "source_index": index}
        rows.append(
            {
                "state": record["state"],
                "questions": {name: record["questions"][name]},
                "_meta": meta,
            }
        )
    return rows


def main() -> None:
    """Write the split files and print their hashes."""
    OUT.mkdir(parents=True, exist_ok=True)
    for name, source in SOURCES.items():
        lines = source.read_text(encoding="utf-8").splitlines()
        rows = [
            row
            for index, line in enumerate(lines)
            if line.strip()
            for row in split_record(json.loads(line), index)
        ]
        target = OUT / name
        text = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
        )
        target.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        print(f"{target.relative_to(ROOT)}: {len(rows)} records, sha256 {digest}")


if __name__ == "__main__":
    main()
