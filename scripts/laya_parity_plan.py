"""Plan and stage the Laya runs of the parity phase (configs/laya_parity.yaml).

    python scripts/laya_parity_plan.py --stage sweep
    python scripts/laya_parity_plan.py --stage finals --top2 lr5e-05 ep6 \
        --selection outputs/reports/laya_parity/sweep_selection.json

Writes `<stage dir>/laya_parity_plan_<stage>.json` (runs, two balanced GPU queues, file hashes,
repository commit) and copies every file the stage needs into the stage directory under a flat
name (Kaggle datasets are flat). Upload the directory as the private Kaggle dataset
`group4-laya-parity` (a new version for the finals stage).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "laya_parity.yaml"
HASHES = ROOT / "data" / "splits" / "laya_parity" / "hashes.json"
STAGE_DIR = ROOT / "outputs" / "drive_stage" / "Group4" / "m5_parity"


def sha256(path: Path) -> str:
    """SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flat(path: str) -> str:
    """A flat file name for a repository path: data/splits/kev/x.jsonl -> kev__x.jsonl."""
    return "__".join(Path(path).relative_to("data/splits").parts)


def run_spec(
    cfg: dict[str, Any], hashes: dict[str, Any], cell: str, setting: str, seed: int
) -> dict[str, Any]:
    """One run: merged parameters, its training file and an estimate of its minutes."""
    params = {**cfg["default"], **(cfg["sweep"].get(setting) or {})}
    data = f"data/splits/laya_parity/{cell}/s{seed}_e{params['epochs']}.jsonl.gz"
    entry = hashes["files"][data]
    prefix = {"domain": "laya_dom", "joint": "laya_joint", "joint_heldout": "laya_heldout_joint"}[
        cell
    ]
    return {
        "run_id": f"{prefix}_{setting}_s{seed}",
        "cell": cell,
        "setting": setting,
        "seed": seed,
        "params": params,
        "data": data,
        "data_file": flat(data),
        "data_sha256": entry["sha256"],
        "item_passes": entry["rows"],
        "est_minutes": round(entry["rows"] / 1000 * cfg["minutes_per_1000_passes"], 1),
        "evaluation": "domain" if cell == "domain" else "joint",
    }


def balance(runs: list[dict[str, Any]], gpus: int = 2) -> list[list[str]]:
    """Longest run first onto the least loaded GPU queue."""
    queues: list[list[str]] = [[] for _ in range(gpus)]
    load = [0.0] * gpus
    for run in sorted(runs, key=lambda r: -r["est_minutes"]):
        i = load.index(min(load))
        queues[i].append(run["run_id"])
        load[i] += run["est_minutes"]
    return queues


def git(*args: str) -> str:
    """Output of a git command in the repository."""
    return subprocess.run(  # noqa: S603 - fixed git command, no user input
        ["git", *args],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    """Write the plan of one stage and stage its files."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--stage", choices=["sweep", "finals"], required=True)
    ap.add_argument("--top2", nargs=2, metavar="SETTING")
    ap.add_argument("--selection", type=Path, help="the scored sweep the top 2 come from")
    ap.add_argument("--out", type=Path, default=STAGE_DIR)
    a = ap.parse_args()
    cfg = yaml.safe_load(CONFIG.read_text())
    hashes = json.loads(HASHES.read_text())

    if a.stage == "sweep":
        runs = [run_spec(cfg, hashes, "domain", "def", s) for s in cfg["seeds"]]
        runs += [run_spec(cfg, hashes, "domain", name, 0) for name in cfg["sweep"]]
    else:
        if not a.top2 or not a.selection:
            ap.error("--stage finals needs --top2 and --selection")
        first = a.top2[0]
        if not set(a.top2) <= set(cfg["sweep"]):
            ap.error(f"--top2 must name sweep settings: {sorted(cfg['sweep'])}")
        runs = [run_spec(cfg, hashes, "domain", name, s) for name in a.top2 for s in (1, 2)]
        runs += [run_spec(cfg, hashes, "joint", name, s) for name in a.top2 for s in cfg["seeds"]]
        runs.append(run_spec(cfg, hashes, "joint_heldout", first, 0))

    a.out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for run in runs:
        shutil.copyfile(ROOT / run["data"], a.out / run["data_file"])
        files[run["data_file"]] = run["data_sha256"]
    runner = ROOT / "notebooks" / "laya_parity_runner.py"
    shutil.copyfile(runner, a.out / runner.name)
    files[runner.name] = sha256(runner)
    cells = {run["evaluation"] for run in runs}
    for cell in sorted(cells):
        for item in cfg["evaluation"][cell]:
            src = ROOT / item["file"]
            shutil.copyfile(src, a.out / flat(item["file"]))
            files[flat(item["file"])] = sha256(src)

    plan = {
        "meta": {
            "stage": a.stage,
            "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "repo_commit": git("rev-parse", "HEAD"),
            "repo_dirty": bool(git("status", "--porcelain")),
            "config_sha256": sha256(CONFIG),
            "top2": a.top2,
            "selection": str(a.selection) if a.selection else None,
            "selection_sha256": sha256(a.selection) if a.selection else None,
        },
        "laya_version": cfg["laya_version"],
        "base": cfg["base"],
        "evaluation": {cell: cfg["evaluation"][cell] for cell in sorted(cells)},
        "runs": runs,
        "queues": balance(runs),
        "files": files,
    }
    (a.out / f"laya_parity_plan_{a.stage}.json").write_text(json.dumps(plan, indent=2) + "\n")
    est = {
        i: sum(r["est_minutes"] for r in runs if r["run_id"] in q)
        for i, q in enumerate(plan["queues"])
    }
    print(
        json.dumps(
            {"runs": [r["run_id"] for r in runs], "queues": plan["queues"], "est_minutes": est},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
