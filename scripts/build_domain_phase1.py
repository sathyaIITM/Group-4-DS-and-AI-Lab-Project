"""Build the phase-1 (domain only) Kev files from the routing splits.

    python scripts/build_domain_phase1.py

Reads data/splits/kev/{train,calibration,dev_synthetic}.v1.jsonl and writes
data/splits/kev_domain/<split>.v1.jsonl, plus two small files for the Mac dry run:
overfit32.v1.jsonl (32 records from train) and train250.v1.jsonl (250 records from train).
The outputs are derived files and can be rebuilt at any time.
"""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.decisions import phase1  # noqa: E402

SOURCE = ROOT / "data" / "splits" / "kev"
TARGET = ROOT / "data" / "splits" / "kev_domain"


def main() -> None:
    for split in phase1.SPLITS:
        count = phase1.convert_split(SOURCE / f"{split}.v1.jsonl", TARGET / f"{split}.v1.jsonl")
        print(f"{split}: {count} records")
    train = list(phase1.read_jsonl(TARGET / "train.v1.jsonl"))
    for name, size in (("overfit32", 32), ("train250", 250)):
        sample = phase1.subsample(train, size)
        phase1.write_jsonl(TARGET / f"{name}.v1.jsonl", sample)
        labels = Counter(r["questions"]["domain"]["label"] for r in sample)
        print(f"{name}: {len(sample)} records, labels {dict(sorted(labels.items()))}")


if __name__ == "__main__":
    main()
