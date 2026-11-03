"""Run the data-preparation pipeline for one or all configured tables.

    python scripts/run_pipeline.py                  # every table in configs/sources
    python scripts/run_pipeline.py --dataset mandi_daily_prices
    python scripts/run_pipeline.py --approve        # store header snapshot and profile
    python scripts/run_pipeline.py --verify         # recompute catalogue facts from files
    python scripts/run_pipeline.py --dataset X --accept-changes "reason"
                                                    # release reviewed changes

A table with a blocking review item is not published: the last good version stays
live, its review list is written to outputs/review/, and the exit code is 2.
Run from the repository root.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.data import profile as profile_mod  # noqa: E402
from analyst.data import publish  # noqa: E402
from analyst.data.config import load_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dataset", help="dataset id (default: all)")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--approve", action="store_true", help="store header snapshot and profile")
    parser.add_argument("--verify", action="store_true", help="check catalogue against the data")
    parser.add_argument("--force", action="store_true", help="rebuild even if nothing changed")
    parser.add_argument(
        "--accept-changes",
        metavar="REASON",
        help="release changes against the live table that a person has reviewed "
        "(needs --dataset; the reason is kept in the lineage record)",
    )
    args = parser.parse_args()

    import os

    os.chdir(ROOT)
    if args.accept_changes and not args.dataset:
        print("--accept-changes names one dataset: add --dataset")
        return 1
    configs = [c for c in load_all() if args.dataset in (None, c.dataset_id)]
    if not configs:
        print(f"no configuration for {args.dataset!r}")
        return 1
    if args.verify:
        problems = publish.verify_release(configs)
        print("release verified" if not problems else "\n".join(problems))
        return 1 if problems else 0

    catalogue_path = publish.PROCESSED / publish.CATALOGUE
    live = (
        {t["dataset_id"]: t for t in json.loads(catalogue_path.read_text())["tables"]}
        if catalogue_path.exists()
        else {}
    )
    entries, exit_code = [], 0
    for config in configs:
        result = publish.run_with_baseline(config, args.raw_dir, accept_reason=args.accept_changes)
        publish.write_review(result)
        if args.approve and not result.blocked and not result.obs.empty:
            profile_mod.save_approved(
                config.dataset_id, result.columns_seen, profile_mod.profile_obs(result.obs)
            )
            print(f"{config.dataset_id}: header snapshot and profile stored")
        counts = {
            s: sum(1 for i in result.review if i.severity == s) for s in ("block", "warn", "info")
        }
        if result.blocked:
            exit_code = 2
            print(f"{config.dataset_id}: BLOCKED {counts}; last good version stays live")
            continue
        previous = live.get(config.dataset_id)
        same = (
            previous
            and previous["raw_sha256"] == result.lineage["raw_sha256"]
            and previous["config_version"] == config.dataset.config_version
        )
        if same and not args.force:
            print(f"{config.dataset_id}: unchanged (raw checksum and config version match)")
            continue
        entries.append(publish.publish(result))
        print(f"{config.dataset_id}: published {len(result.obs):,} values {counts}")
    if entries:
        publish.update_catalogue(entries)
        publish.write_dim_period()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
