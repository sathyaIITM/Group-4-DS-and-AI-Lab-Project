"""Collate repeated-run score reports into one version-ladder table.

    python scripts/version_ladder.py --set dev \
        --rows v0=outputs/reports/ladder_dev_v0.json v1=outputs/reports/ladder_dev_v1.json \
        --out outputs/reports/version_ladder_dev

Each input is the output of `e2e_eval score` over the repeated runs of one configuration. The
table gives, per configuration, the mean over runs with the minimum and maximum: success,
execution accuracy, wrong-answer rate, abstention precision and recall, latency p50 and p95,
cost per answered question, model calls per answered question, and run-to-run instability.
Writes `<out>.json` and `<out>.md`.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

METRICS: list[tuple[str, str, str]] = [
    # (label, key in a run report, format)
    ("Success", "success_rate", "{:.3f}"),
    ("Execution accuracy", "execution_accuracy", "{:.3f}"),
    ("Wrong-answer rate", "wrong_answer_rate", "{:.3f}"),
    ("Abstention precision", "abstention_precision", "{:.3f}"),
    ("Abstention recall", "abstention_recall", "{:.3f}"),
    ("Latency p50 (s)", "latency_ms.p50", "{:.1f}"),
    ("Latency p95 (s)", "latency_ms.p95", "{:.1f}"),
    ("Cost per answer (USD, est.)", "cost_per_answered_usd_est", "{:.4f}"),
    ("Model calls per answer", "calls_per_answered", "{:.2f}"),
]


def _value(run: dict[str, Any], key: str) -> float | None:
    node: Any = run
    for part in key.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if node is None:
        return None
    value = float(node)
    return value / 1000 if key.startswith("latency_ms") else value


def summarise(report: dict[str, Any]) -> dict[str, Any]:
    runs = report["runs"]
    row: dict[str, Any] = {
        "runs": len(runs),
        "questions": runs[0]["n"] if runs else 0,
        "instability": report.get("run_to_run_instability"),
        "success_ci95_first_run": runs[0].get("success_ci95") if runs else None,
    }
    for label, key, _ in METRICS:
        values = [v for v in (_value(r, key) for r in runs) if v is not None]
        row[label] = (
            {"mean": statistics.fmean(values), "min": min(values), "max": max(values)}
            if values
            else None
        )
    return row


def markdown(rows: dict[str, dict[str, Any]], set_name: str) -> str:
    names = list(rows)
    lines = [
        f"Version ladder on `e2e_{set_name}`: mean over runs (minimum to maximum).",
        "",
        "| Measure | " + " | ".join(names) + " |",
        "| --- | " + " | ".join("---" for _ in names) + " |",
    ]
    for label, _, fmt in METRICS:
        cells = []
        for name in names:
            cell = rows[name].get(label)
            if cell is None:
                cells.append("n/a")
                continue
            mean, low, high = (fmt.format(cell[k]) for k in ("mean", "min", "max"))
            cells.append(mean if low == high else f"{mean} ({low} to {high})")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append(
        "| Runs x questions | "
        + " | ".join(f"{rows[n]['runs']} x {rows[n]['questions']}" for n in names)
        + " |"
    )
    lines.append(
        "| Run-to-run instability | "
        + " | ".join(
            "n/a" if rows[n]["instability"] is None else f"{rows[n]['instability']:.3f}"
            for n in names
        )
        + " |"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Collate a version-ladder table")
    parser.add_argument("--set", required=True, help="dev or test")
    parser.add_argument("--rows", nargs="+", required=True, help="NAME=report.json")
    parser.add_argument("--out", type=Path, required=True, help="output path without suffix")
    args = parser.parse_args()
    rows = {}
    for item in args.rows:
        name, path = item.split("=", 1)
        rows[name] = summarise(json.loads(Path(path).read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"set": args.set, "rows": rows, "sources": dict(r.split("=", 1) for r in args.rows)}
    args.out.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown(rows, args.set), encoding="utf-8")
    print(markdown(rows, args.set))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
