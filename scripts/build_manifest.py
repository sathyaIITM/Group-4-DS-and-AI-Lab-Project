"""Write data/MANIFEST.md: rows, columns and SHA-256 for every prepared data file.

Raw and processed files are not tracked in git; the manifest lets anyone who
regenerates them confirm they hold the same version. Run from any directory:

    python scripts/build_manifest.py
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
GROUPS = {
    "Raw downloads (`data/raw`, not tracked)": sorted((DATA_DIR / "raw").glob("*.csv")),
    "Processed tables (`data/processed`, not tracked)": sorted(
        (DATA_DIR / "processed").glob("*.parquet")
    ),
    "Routing splits (`data/splits/kev`, tracked)": sorted(
        (DATA_DIR / "splits" / "kev").glob("*.v1.jsonl")
    ),
    "Text-to-SQL ground truth (`data/ground_truths`, tracked)": sorted(
        (DATA_DIR / "ground_truths").glob("*.csv")
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def shape(path: Path) -> tuple[int, int | str]:
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path)
        return len(frame), frame.shape[1]
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle), "-"
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    return len(frame), frame.shape[1]


lines = [
    "# Data manifest",
    "",
    f"Produced by `scripts/build_manifest.py` on {date.today().isoformat()}. "
    "Recompute after regenerating any file; a changed hash means a changed version.",
    "",
]
for title, paths in GROUPS.items():
    lines += [
        f"## {title}",
        "",
        "| File | Rows | Columns | Bytes | SHA-256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not paths:
        lines.append("| (none present) | | | | |")
    for path in paths:
        rows, columns = shape(path)
        lines.append(
            f"| `{path.relative_to(ROOT_DIR)}` | {rows:,} | {columns} | {path.stat().st_size:,} | `{sha256(path)}` |"
        )
    lines.append("")

(DATA_DIR / "MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {DATA_DIR / 'MANIFEST.md'}")
