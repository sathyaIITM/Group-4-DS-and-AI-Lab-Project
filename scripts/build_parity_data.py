"""Training files for the Kev-Laya parity runs (docs/specs/kev_laya_parity_protocol.md).

Laya trains on the same rows and the same augmented variants that `kev.train` draws for a Kev
run with the same seed: for every epoch e and record r, `kev.data.augment` with
`random.Random(source_seed(seed, f"{e}:{id}"))` and the `b0` probabilities of
`configs/train.yaml` (p_none 0, p_none_distract 0.12, p_distract 0.15), as in
`kev.train.record_variants` (no none pairs). The E epoch variants are written in sequence; Laya
trains one pass over them, so it takes as many item passes as an E-epoch Kev run.

The held-out-table split (default `srs_imr_state`) drops every record whose template names the
table or whose message or context names its measure, for both models.

Run with the Kev environment (kev.data needs `datasets`):

    ~/kev-src/.venv/bin/python -I scripts/build_parity_data.py --kev-src ~/kev-src --root .

Outputs (git-ignored), gzip-compressed JSONL:
    data/splits/laya_parity/{domain,joint,joint_heldout}/s{seed}_e{epochs}.jsonl.gz
    data/splits/kev/phase2_split/train_heldout_<table>.v2.jsonl   (Kev file of the held-out run)
    data/splits/laya_parity/hashes.json                            (sha256 of every file)
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

Record = dict[str, Any]
P_NONE, P_NONE_DISTRACT, P_DISTRACT = 0.0, 0.12, 0.15
SEEDS = (0, 1, 2)
EPOCHS = (2, 4, 6)  # Laya default 4 and the sweep's x0.5 and x1.5
HELD_OUT_PATTERNS = {"srs_imr_state": re.compile(r"infant mortality|\bIMR\b", re.IGNORECASE)}


def sha256(path: Path) -> str:
    """SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> list[Record]:
    """Records of a JSONL file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def to_laya_row(record: Record) -> Record:
    """`phase1.to_laya_row` for any number of questions: each label moves to `expected`."""
    questions, expected = {}, {}
    for qid, question in record["questions"].items():
        q = dict(question)
        expected[qid] = q.pop("label")
        q.pop("src", None)
        q.setdefault("type", "choice")
        questions[qid] = q
    meta = {"id": record["_meta"]["id"], "question": record["_meta"].get("question")}
    return {"state": record["state"], "questions": questions, "expected": expected, "_meta": meta}


def held_out(record: Record, table: str) -> bool:
    """True when the record's template names the table or its message or context names it."""
    if table in str(record["_meta"].get("template_id", "")):
        return True
    state = record["state"]
    if isinstance(state, dict):
        state = {k: state.get(k) for k in ("user_message", "context")}
    return bool(HELD_OUT_PATTERNS[table].search(json.dumps(state)))


def augmented_rows(
    records: list[Record],
    seed: int,
    epochs: int,
    augment: Callable[..., Record],
    source_seed: Callable[[int, str], int],
) -> list[Record]:
    """Laya rows of the variants `kev.train` draws in each epoch, epoch after epoch."""
    rows = []
    for ep in range(epochs):
        for rec in records:
            rng = random.Random(source_seed(seed, f"{ep}:{rec['_meta']['id']}"))  # noqa: S311
            aug = augment(
                rec, rng, p_none=P_NONE, p_none_distract=P_NONE_DISTRACT, p_distract=P_DISTRACT
            )
            aug["_meta"] = rec["_meta"]
            row = to_laya_row(aug)
            row["_meta"]["epoch"] = ep
            rows.append(row)
    return rows


def write_gz(path: Path, rows: list[Record]) -> None:
    """Gzip-compressed JSONL; mtime 0, so the same rows give the same bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(path, "wb", mtime=0) as f:
        for row in rows:
            f.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))


def main() -> int:
    """Write the Laya parity files, the Kev held-out file and their hashes."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--kev-src", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--table", default="srs_imr_state", choices=sorted(HELD_OUT_PATTERNS))
    a = ap.parse_args()
    sys.path.insert(0, str(a.kev_src.expanduser().resolve()))
    from kev.data import augment, source_seed  # Kev's own augmentation and seeding

    splits = a.root / "data" / "splits"
    sources = {
        "domain": splits / "kev_domain" / "train.v2.jsonl",
        "joint": splits / "kev" / "phase2_split" / "train.v2.jsonl",
    }
    out = splits / "laya_parity"
    hashes: dict[str, Any] = {
        "sources": {
            k: {"path": str(v.relative_to(a.root)), "sha256": sha256(v)} for k, v in sources.items()
        },
        "augmentation": {
            "p_none": P_NONE,
            "p_none_distract": P_NONE_DISTRACT,
            "p_distract": P_DISTRACT,
        },
        "files": {},
    }

    joint = read(sources["joint"])
    kept = [r for r in joint if not held_out(r, a.table)]
    kev_held = splits / "kev" / "phase2_split" / f"train_heldout_{a.table}.v2.jsonl"
    kev_held.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8"
    )
    hashes["held_out"] = {
        "table": a.table,
        "dropped": len(joint) - len(kept),
        "kept": len(kept),
        "kev_file": str(kev_held.relative_to(a.root)),
        "kev_sha256": sha256(kev_held),
    }

    cells = {"domain": read(sources["domain"]), "joint": joint, "joint_heldout": kept}
    for cell, records in cells.items():
        for seed in SEEDS:
            for epochs in EPOCHS:
                path = out / cell / f"s{seed}_e{epochs}.jsonl.gz"
                rows = augmented_rows(records, seed, epochs, augment, source_seed)
                write_gz(path, rows)
                name = str(path.relative_to(a.root))
                hashes["files"][name] = {"rows": len(rows), "sha256": sha256(path)}
                print(f"{name}: {len(rows)} rows")
    (out / "hashes.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(hashes["held_out"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
