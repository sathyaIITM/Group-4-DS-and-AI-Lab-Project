"""Final comparison of the Kev-Laya parity phase on the local machine (protocol Section 6).

    python scripts/parity_final.py

Domain: the four candidates on `dev_human` (temperature fitted on calibration), the gate against
Jev, exact McNemar tests against the most accurate candidate, p95 latency and peak server memory.
Tool: every model on `dev_human` (labels v1.1 = v1 after the re-adjudication), the gate against
Jev. Laya: top-answer agreement between the Kaggle and local predictions. Held-out table: accuracy
on the items about `srs_imr_state`. Writes `outputs/reports/parity_final.json`.
"""

from __future__ import annotations

import json
import re
from math import comb
from pathlib import Path
from statistics import median
from typing import Any

from analyst.evaluation.decision_eval import calibrated_report, labels_of
from analyst.evaluation.decision_eval import read_jsonl as _iter

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "outputs" / "predictions"
LAYA = PRED / "laya_parity"
LOGS = ROOT / "outputs" / "logs"
MARGIN, ECE_MAX = 0.03, 0.10
HELD_OUT = re.compile(r"infant mortality|\bIMR\b", re.IGNORECASE)


def rows(path: Path) -> list[dict[str, Any]]:
    """Rows of a predictions file."""
    return list(_iter(path))


# Domain candidates: (name, calibration file, dev_human file, latency file, memory log)
DOMAIN = {
    "Kev ep3_s2": (
        PRED / "domain_ep3_s2_calibration.jsonl",
        PRED / "domain_ep3_s2_dev_human.jsonl",
        PRED / "domain_ep3_s2_lat_dev_human.jsonl",
        LOGS / "rss_kev_ep3_s2.txt",
    ),
    "Kev joint_lr4e-05_s1": (
        PRED / "domain_joint_lr4e-05_s1_calibration.jsonl",
        PRED / "domain_joint_lr4e-05_s1_dev_human.jsonl",
        PRED / "domain_joint_lr4e-05_s1_lat_dev_human.jsonl",
        LOGS / "rss_kev_joint_lr4e-05_s1.txt",
    ),
    "Laya laya_dom_ep6_s1": (
        PRED / "domain_laya_dom_ep6_s1_mac_calibration.jsonl",
        PRED / "domain_laya_dom_ep6_s1_mac_dev_human.jsonl",
        PRED / "domain_laya_dom_ep6_s1_mac_dev_human.jsonl",
        LOGS / "rss_laya_dom_ep6_s1.txt",
    ),
    "Laya laya_joint_lr5e-05_s1": (
        PRED / "domain_laya_joint_lr5e-05_s1_mac_calibration.jsonl",
        PRED / "domain_laya_joint_lr5e-05_s1_mac_dev_human.jsonl",
        PRED / "domain_laya_joint_lr5e-05_s1_mac_dev_human.jsonl",
        LOGS / "rss_laya_joint_lr5e-05_s1.txt",
    ),
}
# Tool systems: (name, calibration file or None for raw, dev_human file)
TOOL = {
    "Jev (zero-shot)": (None, PRED / "tool_jev_dev_human.jsonl"),
    "Kev zero-shot": (None, PRED / "tool_zeroshot_v2_dev_human.jsonl"),
    **{
        f"Kev joint_lr4e-05_s{s}": (
            PRED / f"tool_joint_lr4e-05_s{s}_calibration.jsonl",
            PRED / f"tool_joint_lr4e-05_s{s}_dev_human.jsonl",
        )
        for s in (0, 1, 2)
    },
    "Kev joint_ep3_s1 (phase 2)": (
        PRED / "tool_joint_ep3_s1_calibration.jsonl",
        PRED / "tool_joint_ep3_s1_dev_human.jsonl",
    ),
    "Laya laya_joint_lr5e-05_s0 (Kaggle)": (
        LAYA / "laya_joint_lr5e-05_s0" / "tool_calibration.jsonl",
        LAYA / "laya_joint_lr5e-05_s0" / "SEALED_tool_dev_human.jsonl",
    ),
    "Laya laya_joint_lr5e-05_s1": (
        PRED / "tool_laya_joint_lr5e-05_s1_mac_calibration.jsonl",
        PRED / "tool_laya_joint_lr5e-05_s1_mac_dev_human.jsonl",
    ),
    "Laya laya_joint_lr5e-05_s2 (Kaggle)": (
        LAYA / "laya_joint_lr5e-05_s2" / "tool_calibration.jsonl",
        LAYA / "laya_joint_lr5e-05_s2" / "SEALED_tool_dev_human.jsonl",
    ),
}


def report(cal: Path | None, dev: Path, decision: str) -> dict[str, Any]:
    """Calibrated report (temperature from `cal`), or the raw one when there is no calibration."""
    dev_rows = rows(dev)
    if cal is None:
        r = calibrated_report(dev_rows, dev_rows, labels_of(decision))["dev_raw"]
        r["temperature"] = 1.0
        return r
    return calibrated_report(rows(cal), dev_rows, labels_of(decision))["dev_calibrated"]


def correct(path: Path) -> dict[str, bool]:
    """Item id -> top answer correct."""
    return {r["id"]: r["predicted"] == r["label"] for r in rows(path)}


def mcnemar(a: dict[str, bool], b: dict[str, bool]) -> dict[str, Any]:
    """Exact two-sided McNemar test on the discordant items."""
    only_a = sum(a[i] and not b[i] for i in a)
    only_b = sum(b[i] and not a[i] for i in a)
    n, k = only_a + only_b, min(only_a, only_b)
    p = min(1.0, 2 * sum(comb(n, j) for j in range(k + 1)) / 2**n) if n else 1.0
    return {"only_first": only_a, "only_second": only_b, "p": round(p, 4)}


def latency(path: Path) -> dict[str, float]:
    """p50 and p95 seconds per decision."""
    xs = sorted(r["latency_s"] for r in rows(path))
    return {"p50": round(median(xs), 3), "p95": round(xs[int(0.95 * (len(xs) - 1))], 3)}


def peak_mb(path: Path) -> float | None:
    """Peak resident memory of the server process tree (MB), sampled every 2 s."""
    xs = [float(x) for x in path.read_text().split() if x.strip()]
    return round(max(xs) / 1024, 0) if xs else None


def summary(r: dict[str, Any]) -> dict[str, Any]:
    """The figures the report cites."""
    return {
        "n": r["n"],
        "accuracy": round(r["accuracy"], 3),
        "accuracy_ci95": [round(x, 3) for x in r["accuracy_ci95"]],
        "macro_f1": round(r["macro_f1"], 3),
        "ece": round(r["ece"], 3),
        "nll": round(r["nll"], 4),
        "temperature": round(r["temperature"], 3),
    }


def held_out_ids() -> set[str]:
    """dev_human items about srs_imr_state (same filter as scripts/build_parity_data.py)."""
    items = ROOT / "data" / "labels" / "dev_human_v1" / "items.jsonl"
    out = set()
    for r in rows(items):
        text = r["message"] + " " + json.dumps(r.get("context") or {})
        if HELD_OUT.search(text):
            out.add(r["id"])
    return out


def main() -> int:
    """Write outputs/reports/parity_final.json and print it."""
    jev_domain = summary(
        report(
            PRED / "domain_jev_v2_calibration.jsonl", PRED / "domain_jev_dev_human.jsonl", "domain"
        )
    )
    domain: dict[str, Any] = {}
    for name, (cal, dev, lat, mem) in DOMAIN.items():
        s = summary(report(cal, dev, "domain"))
        s["gate"] = bool(s["accuracy"] >= jev_domain["accuracy"] - MARGIN and s["ece"] <= ECE_MAX)
        s["latency_s"] = latency(lat)
        s["peak_rss_mb"] = peak_mb(mem)
        domain[name] = s
    best = max(domain, key=lambda k: domain[k]["accuracy"])
    for name in domain:
        if name != best:
            domain[name]["mcnemar_vs_best"] = mcnemar(
                correct(DOMAIN[best][1]), correct(DOMAIN[name][1])
            )
    jev_tool = summary(report(None, PRED / "tool_jev_dev_human.jsonl", "tool"))
    tool: dict[str, Any] = {}
    for name, (cal, dev) in TOOL.items():
        s = summary(report(cal, dev, "tool"))
        s["gate"] = bool(s["accuracy"] >= jev_tool["accuracy"] - MARGIN and s["ece"] <= ECE_MAX)
        tool[name] = s
    served = PRED / "tool_joint_lr4e-05_s1_dev_human.jsonl"
    tool_tests = {
        "Kev joint_lr4e-05_s1 vs Jev": mcnemar(
            correct(served), correct(TOOL["Jev (zero-shot)"][1])
        ),
        "Kev joint_lr4e-05_s1 vs Laya laya_joint_lr5e-05_s1": mcnemar(
            correct(served), correct(TOOL["Laya laya_joint_lr5e-05_s1"][1])
        ),
    }
    agreement = {}
    for run, decisions in (
        ("laya_dom_ep6_s1", ("domain",)),
        ("laya_joint_lr5e-05_s1", ("domain", "tool")),
    ):
        for dec in decisions:
            for split in ("calibration", "dev_synthetic", "dev_human"):
                name = f"{dec}_{split}.jsonl"
                k = (
                    LAYA
                    / run
                    / (f"SEALED_{name}" if (dec, split) == ("tool", "dev_human") else name)
                )
                m = PRED / f"{dec}_{run}_mac_{split}.jsonl"
                a = {r["id"]: r["predicted"] for r in rows(k)}
                b = {r["id"]: r["predicted"] for r in rows(m)}
                agreement[f"{run}/{dec}/{split}"] = round(sum(a[i] == b[i] for i in a) / len(a), 4)
    held = held_out_ids()
    held_out = {}
    for name, path in (
        ("Kev joint_lr4e-05_s1 (served joint)", PRED / "domain_joint_lr4e-05_s1_dev_human.jsonl"),
        ("Kev heldout_joint_ep3_s0", PRED / "domain_heldout_joint_ep3_s0_dev_human.jsonl"),
        ("Kev joint_ep3_s2 (same setting)", PRED / "domain_joint_ep3_s2_dev_human.jsonl"),
        (
            "Laya laya_joint_ep6_s0 (same setting)",
            LAYA / "laya_joint_ep6_s0" / "domain_dev_human.jsonl",
        ),
        (
            "Laya laya_heldout_joint_ep6_s0",
            LAYA / "laya_heldout_joint_ep6_s0" / "domain_dev_human.jsonl",
        ),
    ):
        c = correct(path)
        ids = [i for i in c if i in held]
        held_out[name] = {"items": len(ids), "correct": sum(c[i] for i in ids)}
    for name, path in (
        ("Kev heldout_joint_ep3_s0", PRED / "tool_heldout_joint_ep3_s0_dev_human.jsonl"),
        (
            "Laya laya_heldout_joint_ep6_s0",
            LAYA / "laya_heldout_joint_ep6_s0" / "SEALED_tool_dev_human.jsonl",
        ),
    ):
        if path.exists():
            c = correct(path)
            ids = [i for i in c if i in held]
            held_out[name + " tool"] = {"items": len(ids), "correct": sum(c[i] for i in ids)}
    out = {
        "jev_domain": jev_domain,
        "domain": domain,
        "domain_most_accurate": best,
        "jev_tool": jev_tool,
        "tool": tool,
        "tool_mcnemar": tool_tests,
        "laya_kaggle_vs_local_agreement": agreement,
        "held_out_table": {"table": "srs_imr_state", "dev_human_ids": sorted(held), **held_out},
    }
    (ROOT / "outputs" / "reports" / "parity_final.json").write_text(
        json.dumps(out, indent=2) + "\n"
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
