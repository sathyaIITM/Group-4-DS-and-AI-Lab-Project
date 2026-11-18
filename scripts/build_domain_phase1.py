"""Build the phase-1 (domain only) Kev files from the routing splits.

    python scripts/build_domain_phase1.py --version v2
    python scripts/build_domain_phase1.py --version v1

Reads data/splits/kev/{train,calibration,dev_synthetic}.<version>.jsonl and writes
data/splits/kev_domain/<split>.<version>.jsonl, plus two small files for dry and smoke runs:
overfit32.<version>.jsonl (32 records from train) and train250.<version>.jsonl (250 records
from train). With --laya, the same records are also written as Laya training rows
(data/splits/laya_domain/<split>.<version>.jsonl). The outputs are derived files and can be
rebuilt at any time; their SHA-256 values are listed in data/MANIFEST.md.

After the dev_human freeze (data/splits/kev/dev_human.v1.jsonl), the same script writes the
frozen set as Kev records with both routing questions, for Kev, Jev and Laya alike:

    python scripts/build_domain_phase1.py --dev-human data/splits/kev/dev_human.v1.jsonl
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.decisions import phase1  # noqa: E402

SOURCE = ROOT / "data" / "splits" / "kev"
TARGET = ROOT / "data" / "splits" / "kev_domain"
LAYA_TARGET = ROOT / "data" / "splits" / "laya_domain"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the phase-1 domain files.")
    parser.add_argument("--version", default="v2", choices=["v1", "v2"])
    parser.add_argument("--laya", action="store_true", help="also write Laya training rows")
    parser.add_argument("--dev-human", type=Path, help="the frozen dev_human file to convert")
    args = parser.parse_args()
    if args.dev_human:
        records = [phase1.dev_human_record(r) for r in phase1.read_jsonl(args.dev_human)]
        target = TARGET / "dev_human.v1.jsonl"
        phase1.write_jsonl(target, records)
        print(f"dev_human: {len(records)} records -> {target.relative_to(ROOT)}")
        return
    version = args.version
    for split in phase1.SPLITS:
        source = SOURCE / f"{split}.{version}.jsonl"
        count = phase1.convert_split(source, TARGET / f"{split}.{version}.jsonl")
        print(f"{split}: {count} records")
    train = list(phase1.read_jsonl(TARGET / f"train.{version}.jsonl"))
    for name, size in (("overfit32", 32), ("train250", 250)):
        sample = phase1.subsample(train, size)
        phase1.write_jsonl(TARGET / f"{name}.{version}.jsonl", sample)
        labels = Counter(r["questions"]["domain"]["label"] for r in sample)
        print(f"{name}: {len(sample)} records, labels {dict(sorted(labels.items()))}")
    if args.laya:
        for name in (*phase1.SPLITS, "overfit32", "train250"):
            records = phase1.read_jsonl(TARGET / f"{name}.{version}.jsonl")
            target = LAYA_TARGET / f"{name}.{version}.jsonl"
            phase1.write_jsonl(target, (phase1.to_laya_row(r) for r in records))
            print(f"laya {name}: {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
