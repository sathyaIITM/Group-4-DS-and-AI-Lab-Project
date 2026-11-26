"""Table of every run of the Kev-Laya parity phase (docs/specs/kev_laya_parity_protocol.md).

    python scripts/parity_run_table.py

One row per run: model, cell, setting, seed, platform, session, wall time, data hash, weights
hash and the selection score (dev_synthetic NLL after the temperature fitted on calibration; the
mean of the domain and tool NLL in the joint cell). Kev rows come from `models/registry.json`
and the Kev reports; Laya rows from the run records the Kaggle notebook wrote
(`outputs/predictions/laya_parity/<run>/environment.json`) and `outputs/reports/laya_parity`.
Writes `outputs/reports/parity_runs.csv` and `outputs/reports/parity_runs.md`.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "outputs" / "reports"
LAYA_PRED = ROOT / "outputs" / "predictions" / "laya_parity"
LAYA_REPORTS = REPORTS / "laya_parity"

# Kev runs of the phase: (run id, cell, setting, seed); the domain sweep of Milestone 4 included
KEV_RUNS = [
    *[(f"b0_s{s}", "domain", "b0", s) for s in (0, 1, 2)],
    ("lr1e-05", "domain sweep", "lr1e-05", 0),
    ("ep1", "domain sweep", "ep1", 0),
    ("ep3", "domain", "ep3", 0),
    ("ep3_s1", "domain", "ep3", 1),
    ("ep3_s2", "domain", "ep3", 2),
    ("lr4e-05", "domain", "lr4e-05", 0),
    ("lr4e-05_s1", "domain", "lr4e-05", 1),
    ("lr4e-05_s2", "domain", "lr4e-05", 2),
    *[(f"joint_ep3_s{s}", "joint", "ep3", s) for s in (0, 1, 2)],
    *[(f"joint_lr4e-05_s{s}", "joint", "lr4e-05", s) for s in (0, 1, 2)],
    ("heldout_joint_ep3_s0", "held-out table", "ep3", 0),
]
NEW_KEV = {
    "ep3_s1",
    "ep3_s2",
    "lr4e-05_s1",
    "lr4e-05_s2",
    "joint_ep3_s2",
    "joint_lr4e-05_s0",
    "joint_lr4e-05_s1",
    "joint_lr4e-05_s2",
    "heldout_joint_ep3_s0",
}
COLUMNS = [
    "model",
    "run_id",
    "cell",
    "setting",
    "seed",
    "phase",
    "platform",
    "session",
    "wall_minutes",
    "selection_nll",
    "domain_nll",
    "tool_nll",
    "data_sha256",
    "weights_sha256",
]


def nll(path: Path) -> float | None:
    """dev_synthetic NLL after temperature from a score report, if it exists."""
    if not path.exists():
        return None
    return float(json.loads(path.read_text())["dev_calibrated"]["nll"])


def kev_rows(registries: list[Path], kev_reports: Path) -> list[dict[str, Any]]:
    """Rows of the Kev runs (the first registry that holds a run wins)."""
    entries: dict[str, Any] = {}
    for registry in registries:
        for e in json.loads(registry.read_text()):
            entries.setdefault(e["run_id"], e)
    rows = []
    for run_id, cell, setting, seed in KEV_RUNS:
        e = entries.get(run_id, {})
        dom = nll(kev_reports / f"score_domain_{run_id}.json")
        tool = nll(kev_reports / f"score_tool_{run_id}.json")
        scores = [x for x in (dom, tool) if x is not None]
        env = e.get("environment") or {}
        rows.append(
            {
                "model": "Kev-0.8B",
                "run_id": run_id,
                "cell": cell,
                "setting": setting,
                "seed": seed,
                "phase": "parity (new)" if run_id in NEW_KEV else "earlier, reused",
                "platform": e.get("platform"),
                "session": env.get("session"),
                "wall_minutes": round(e["wall_seconds"] / 60, 1) if e.get("wall_seconds") else None,
                "selection_nll": round(mean(scores), 5) if scores else None,
                "domain_nll": round(dom, 5) if dom is not None else None,
                "tool_nll": round(tool, 5) if tool is not None else None,
                "data_sha256": e.get("data_sha256"),
                "weights_sha256": (e.get("weights_sha256") or {}).get("adapter_model.safetensors"),
            }
        )
    return rows


def laya_sessions() -> dict[str, str]:
    """Kaggle session of each Laya run, from the staged plans: K1 (sweep) or K3 part N."""
    stage = ROOT / "outputs" / "drive_stage" / "Group4"
    out = {}
    sweep = stage / "m5_parity" / "laya_parity_plan_sweep.json"
    if sweep.exists():
        out |= {r["run_id"]: "K1" for r in json.loads(sweep.read_text())["runs"]}
    finals = stage / "m5_parity_finals" / "laya_parity_plan_finals.json"
    if finals.exists():
        for i, part in enumerate(json.loads(finals.read_text()).get("parts", [])):
            out |= {run: f"K3 part {i}" for queue in part for run in queue}
    return out


def laya_rows() -> list[dict[str, Any]]:
    """Rows of the Laya runs (sweep and finals)."""
    sessions = laya_sessions()
    rows = []
    for env_path in sorted(LAYA_PRED.glob("laya_*/environment.json")):
        rec = json.loads(env_path.read_text())
        spec, run_id = rec["spec"], rec["run_id"]
        cell = {"domain": "domain", "joint": "joint", "joint_heldout": "held-out table"}[
            spec["cell"]
        ]
        session = sessions.get(run_id)
        stage = "sweep" if session == "K1" else "finals"
        dom = nll(LAYA_REPORTS / f"score_domain_{run_id}.json")
        tool = nll(LAYA_REPORTS / f"score_tool_{run_id}.json")
        scores = [x for x in (dom, tool) if x is not None]
        rows.append(
            {
                "model": "Laya",
                "run_id": run_id,
                "cell": cell,
                "setting": spec["setting"],
                "seed": spec["seed"],
                "phase": f"parity (new), {stage}",
                "platform": "kaggle",
                "session": session,
                "wall_minutes": round(rec["train_seconds"] / 60, 1),
                "selection_nll": round(mean(scores), 5) if scores else None,
                "domain_nll": round(dom, 5) if dom is not None else None,
                "tool_nll": round(tool, 5) if tool is not None else None,
                "data_sha256": spec["data_sha256"],
                "weights_sha256": rec["weights_sha256"],
            }
        )
    return rows


def main() -> int:
    """Write the run table."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument(
        "--registry",
        type=Path,
        nargs="+",
        default=[ROOT / "models" / "registry.json"],
        help="registries to read, first wins (another checkout may hold runs not merged yet)",
    )
    ap.add_argument("--kev-reports", type=Path, default=REPORTS, help="Kev score_*.json reports")
    a = ap.parse_args()
    rows = kev_rows(a.registry, a.kev_reports) + laya_rows()
    with (REPORTS / "parity_runs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    shown = [c for c in COLUMNS if c not in ("data_sha256", "weights_sha256")]
    lines = ["| " + " | ".join(shown) + " |", "| " + " | ".join("---" for _ in shown) + " |"]
    lines += [
        "| " + " | ".join("" if r[c] is None else str(r[c]) for c in shown) + " |" for r in rows
    ]
    (REPORTS / "parity_runs.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    new = sum(r["phase"].startswith("parity") for r in rows)
    print(f"{len(rows)} rows ({new} new in the parity phase) -> outputs/reports/parity_runs.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
