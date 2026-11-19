"""Flag dev_human items whose wording is close to a training or evaluation message.

    python scripts/check_dev_human_overlap.py \
        --items data/labels/dev_human_v1/items.jsonl \
        --reference data/splits/kev/train.v2.jsonl data/splits/kev/calibration.v2.jsonl \
                    data/splits/kev/dev_synthetic.v2.jsonl data/eval/e2e_v1.jsonl \
        --out data/labels/dev_human_v1/overlap_check.json

An item is flagged at a character 5-gram Jaccard similarity of 0.8 or more (T3 brief,
Section 6). Flagged items are rewritten and the check is run again; the final output is
committed. Exit code 1 while any item is flagged.
"""

import argparse
import json
import sys
from pathlib import Path

from analyst.evaluation.dev_human import OVERLAP_THRESHOLD, messages_of, overlap, read_jsonl


def main() -> int:
    """Flag dev-human items that are near-duplicates of reference items."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--reference", type=Path, nargs="+", required=True)
    parser.add_argument("--threshold", type=float, default=OVERLAP_THRESHOLD)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    missing = [str(p) for p in args.reference if not p.exists()]
    if missing:
        parser.error(f"reference files not found: {missing}")
    references = {str(p): messages_of(p) for p in args.reference}
    result = overlap(read_jsonl(args.items), references, args.threshold)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(f"{len(result['flagged'])} of {result['items']} items flagged at J >= {args.threshold}")
    for row in result["flagged"]:
        print(f"  {row['id']} J={row['jaccard']}: {row['message']!r} ~ {row['closest']!r}")
    return 1 if result["flagged"] else 0


if __name__ == "__main__":
    sys.exit(main())
