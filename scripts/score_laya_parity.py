"""Score parity-phase runs and apply the selection rules (docs/specs/kev_laya_parity_protocol.md).

    # Laya: predictions written by the Kaggle notebook, unzipped under --pred-root/<run>/
    python scripts/score_laya_parity.py laya --stage sweep \
        --plan outputs/drive_stage/Group4/m5_parity/laya_parity_plan_sweep.json
    python scripts/score_laya_parity.py laya --stage finals --plan .../laya_parity_plan_finals.json

    # Kev: the same rules on the Kev reports (outputs/reports/score_<decision>_<run>.json)
    python scripts/score_laya_parity.py kev --stage sweep
    python scripts/score_laya_parity.py kev --stage finals

Per run and decision: one temperature fitted on calibration, dev_synthetic scored raw and scaled
(`decision_eval.calibrated_report`), and dev_human domain scored with the same temperature.
Files named SEALED_* (dev_human tool) are never read. Selection uses dev_synthetic only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from analyst.evaluation.decision_eval import calibrated_report, labels_of, sha256_of
from analyst.evaluation.decision_eval import read_jsonl as _iter_jsonl

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "outputs" / "reports"
KEV_SWEEP = ["lr1e-05", "lr4e-05", "ep1", "ep3"]  # one factor at a time around B0 (b0_s0..s2)
KEV_CELLS = {
    "domain": {  # the default B0 competes with its three seeds (protocol Section 4)
        "b0": ["b0_s0", "b0_s1", "b0_s2"],
        "ep3": ["ep3", "ep3_s1", "ep3_s2"],
        "lr4e-05": ["lr4e-05", "lr4e-05_s1", "lr4e-05_s2"],
    },
    "joint": {
        "ep3": ["joint_ep3_s0", "joint_ep3_s1", "joint_ep3_s2"],
        "lr4e-05": ["joint_lr4e-05_s0", "joint_lr4e-05_s1", "joint_lr4e-05_s2"],
    },
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """All rows of a JSONL file (the library helper is a generator)."""
    return list(_iter_jsonl(path))


def nll(report: dict[str, Any]) -> float:
    """dev_synthetic NLL after the temperature fitted on calibration."""
    return float(report["dev_calibrated"]["nll"])


def macro_f1(report: dict[str, Any]) -> float:
    """dev_synthetic macro-F1 after temperature."""
    return float(report["dev_calibrated"]["macro_f1"])


def score_laya_run(pred: Path, run_id: str, out: Path) -> dict[str, dict[str, Any]]:
    """Reports of one Laya run, written to `out`; returns {decision: dev_synthetic report}."""
    reports = {}
    for decision in ("domain", "tool"):
        cal, dev = pred / f"{decision}_calibration.jsonl", pred / f"{decision}_dev_synthetic.jsonl"
        if not cal.exists():
            continue
        labels = labels_of(decision)
        calibration = read_jsonl(cal)
        report = calibrated_report(calibration, read_jsonl(dev), labels)
        report["inputs_sha256"] = {"calibration": sha256_of(cal), "dev": sha256_of(dev)}
        (out / f"score_{decision}_{run_id}.json").write_text(json.dumps(report, indent=2) + "\n")
        reports[decision] = report
        human = pred / f"{decision}_dev_human.jsonl"  # domain only; tool is SEALED_
        if human.exists():
            r = calibrated_report(calibration, read_jsonl(human), labels)
            r["inputs_sha256"] = {"calibration": sha256_of(cal), "dev": sha256_of(human)}
            (out / f"score_{decision}_{run_id}_dev_human.json").write_text(
                json.dumps(r, indent=2) + "\n"
            )
    return reports


def run_nll(reports: dict[str, dict[str, Any]]) -> float:
    """Selection loss of a run: dev_synthetic NLL (mean over decisions in the joint cell)."""
    return mean(nll(r) for r in reports.values())


def run_f1(reports: dict[str, dict[str, Any]]) -> float:
    """Tie-break of a run: dev_synthetic macro-F1 (mean over decisions)."""
    return mean(macro_f1(r) for r in reports.values())


def top2(sweep: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """The two non-default sweep settings with the lowest NLL (macro-F1 breaks ties)."""
    ranked = sorted(sweep, key=lambda s: (run_nll(sweep[s]), -run_f1(sweep[s])))
    table = [
        {"setting": s, "nll": round(run_nll(sweep[s]), 5), "macro_f1": round(run_f1(sweep[s]), 4)}
        for s in ranked
    ]
    return {"ranking": table, "top2": ranked[:2]}


def cell_choice(cells: dict[str, dict[str, list[dict[str, dict[str, Any]]]]]) -> dict[str, Any]:
    """Per cell: the setting with the lowest mean NLL over its three seeds; served seed = lowest."""
    out = {}
    for cell, settings in cells.items():
        rows = {}
        for setting, runs in settings.items():
            losses = [run_nll(r) for r in runs]
            rows[setting] = {
                "seed_nll": [round(x, 5) for x in losses],
                "mean_nll": round(mean(losses), 5),
                "range": round(max(losses) - min(losses), 5),
                "mean_macro_f1": round(mean(run_f1(r) for r in runs), 4),
            }
        best = min(rows, key=lambda s: (rows[s]["mean_nll"], -rows[s]["mean_macro_f1"]))
        served = min(range(len(rows[best]["seed_nll"])), key=lambda i: rows[best]["seed_nll"][i])
        out[cell] = {"settings": rows, "chosen": best, "served_seed_index": served}
    return out


def kev_report(
    run_id: str, decisions: tuple[str, ...], reports: Path = REPORTS
) -> dict[str, dict[str, Any]]:
    """Kev reports of one run, as written by scripts/score_kev_run.sh and decision_eval score."""
    return {d: json.loads((reports / f"score_{d}_{run_id}.json").read_text()) for d in decisions}


def main() -> int:
    """Score and select for one model and stage."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("model", choices=["laya", "kev"])
    ap.add_argument("--stage", choices=["sweep", "finals"], required=True)
    ap.add_argument("--plan", type=Path, help="Laya plan file of the stage")
    ap.add_argument(
        "--pred-root", type=Path, default=ROOT / "outputs" / "predictions" / "laya_parity"
    )
    ap.add_argument("--out", type=Path, default=REPORTS / "laya_parity")
    ap.add_argument(
        "--kev-reports", type=Path, default=REPORTS, help="where the Kev score_*.json reports are"
    )
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    if a.model == "laya":
        if not a.plan:
            ap.error("laya needs --plan")
        plan = json.loads(a.plan.read_text())
        runs = {r["run_id"]: r for r in plan["runs"]}
        scored = {rid: score_laya_run(a.pred_root / rid, rid, a.out) for rid in runs}
        if a.stage == "sweep":
            sweep = {r["setting"]: scored[rid] for rid, r in runs.items() if r["setting"] != "def"}
            result: dict[str, Any] = top2(sweep)
            result["default_seed_nll"] = [
                round(run_nll(scored[rid]), 5) for rid, r in runs.items() if r["setting"] == "def"
            ]
        else:
            # the default competes in the domain cell with its three sweep seeds
            cells: dict[str, dict[str, list[Any]]] = {"domain": {"def": []}, "joint": {}}
            sweep_dir = a.out
            for r in runs.values():
                if r["cell"] in cells:
                    cells[r["cell"]].setdefault(r["setting"], [])
            for cell, settings in cells.items():
                prefix = "laya_dom" if cell == "domain" else "laya_joint"
                for setting in settings:
                    for seed in (0, 1, 2):
                        rid = f"{prefix}_{setting}_s{seed}"
                        decisions = ("domain",) if cell == "domain" else ("domain", "tool")
                        settings[setting].append(
                            {
                                d: json.loads((sweep_dir / f"score_{d}_{rid}.json").read_text())
                                for d in decisions
                            }
                        )
            result = cell_choice(cells)
    elif a.stage == "sweep":
        result = top2({rid: kev_report(rid, ("domain",), a.kev_reports) for rid in KEV_SWEEP})
        result["default_seed_nll"] = [
            round(run_nll(kev_report(f"b0_s{s}", ("domain",), a.kev_reports)), 5) for s in (0, 1, 2)
        ]
    else:
        result = cell_choice(
            {
                "domain": {
                    k: [kev_report(r, ("domain",), a.kev_reports) for r in v]
                    for k, v in KEV_CELLS["domain"].items()
                },
                "joint": {
                    k: [kev_report(r, ("domain", "tool"), a.kev_reports) for r in v]
                    for k, v in KEV_CELLS["joint"].items()
                },
            }
        )
    result["model"], result["stage"] = a.model, a.stage
    path = a.out / f"selection_{a.model}_{a.stage}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
