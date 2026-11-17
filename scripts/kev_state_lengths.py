"""State lengths of Kev training files in Qwen tokens, and whether each record fits kev.train.

kev.train drops (does not truncate) a training record whose state, branch or packed row
exceeds the training context, and the server cuts an over-long state to its first
max_state tokens. This script uses Kev's own encoder and fit check, so it runs with the Kev
environment (Kev commit as in configs/train.yaml):

    cd "$KEV_DIR" && HF_HUB_OFFLINE=1 .venv/bin/python -I \
        <repo>/scripts/kev_state_lengths.py --max-state 384 \
        --out <repo>/outputs/reports/kev_state_lengths_v2.json \
        <repo>/data/splits/kev_domain/{train,calibration,dev_synthetic}.v2.jsonl
"""

import argparse
import json
import statistics
from pathlib import Path

from kev.data import load_records, materialize
from kev.model import encode, fits, load_tokenizer, training_context

BASE = "Qwen/Qwen3.5-0.8B-Base"
BASE_REVISION = "dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--max-state", type=int, default=384)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    tokenizer = load_tokenizer(BASE, BASE_REVISION)
    context = training_context(args.max_state)
    result = {"tokenizer": f"{BASE}@{BASE_REVISION}", "max_state": args.max_state, "files": {}}
    for path in args.files:
        lengths, dropped = [], 0
        for record in load_records(str(path)):
            request = materialize(record)
            encoded = encode(tokenizer, request, max_state=10**6, max_branch=10**6)
            lengths.append(encoded["state_tokens"])
            if not fits(request, tokenizer, **context):
                dropped += 1
        lengths.sort()
        result["files"][path.name] = {
            "records": len(lengths),
            "state_tokens_median": statistics.median(lengths),
            "state_tokens_p95": lengths[int(0.95 * (len(lengths) - 1))],
            "state_tokens_max": lengths[-1],
            "over_max_state": sum(n > args.max_state for n in lengths),
            "would_be_dropped_by_kev_train": dropped,
        }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
