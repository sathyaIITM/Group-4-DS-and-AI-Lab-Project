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
    """Return a metric from a run report by dotted key, latency in seconds."""
    node: Any = run
    for part in key.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if node is None:
        return None
    value = float(node)
    return value / 1000 if key.startswith("latency_ms") else value


ACTIONS = ("answer", "clarify", "decline", "describe", "search")


def by_action(report: dict[str, Any]) -> dict[str, dict[str, float | int]]:
    """Success per expected action over all runs, read from each run's predictions with the
    scorer's own success rule (so a version can be compared where it differs, not only in
    total)."""
    from analyst.evaluation.e2e_eval import _case_success

    counts: dict[str, list[int]] = {}
    for run in report["runs"]:
        path = Path(run["path"])
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                case = json.loads(line)
                cell = counts.setdefault(case.get("expected_action", "?"), [0, 0])
                cell[0] += int(_case_success(case))
                cell[1] += 1
    return {k: {"success": v[0] / v[1], "cases": v[1]} for k, v in counts.items() if v[1]}


def summarise(report: dict[str, Any]) -> dict[str, Any]:
    """Return the mean, minimum and maximum of each metric over a configuration's runs."""
    runs = report["runs"]
    row: dict[str, Any] = {
        "runs": len(runs),
        "questions": runs[0]["n"] if runs else 0,
        "instability": report.get("run_to_run_instability"),
        "success_ci95_first_run": runs[0].get("success_ci95") if runs else None,
        "by_action": by_action(report),
    }
    for label, key, _ in METRICS:
        values = [v for v in (_value(r, key) for r in runs) if v is not None]
        row[label] = (
            {"mean": statistics.fmean(values), "min": min(values), "max": max(values)}
            if values
            else None
        )
    return row


def markdown(rows: dict[str, dict[str, Any]], set_name: str, scorer: str = "v2") -> str:
    """Render the version-ladder tables as Markdown."""
    names = list(rows)
    lines = [
        f"Version ladder on `e2e_{set_name}` (scorer rules {scorer}): mean over runs"
        " (minimum to maximum).",
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
    lines += ["", "Success by expected action (all runs pooled; cases in brackets).", ""]
    lines.append("| Expected action | " + " | ".join(names) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in names) + " |")
    for action in ACTIONS:
        cells = []
        for name in names:
            cell = rows[name].get("by_action", {}).get(action)
            cells.append("n/a" if cell is None else f"{cell['success']:.3f} ({cell['cases']})")
        if any(c != "n/a" for c in cells):
            lines.append(f"| {action} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Command-line entry point for the version-ladder table."""
    parser = argparse.ArgumentParser(description="Collate a version-ladder table")
    parser.add_argument("--set", required=True, help="dev or test")
    parser.add_argument("--rows", nargs="+", required=True, help="NAME=report.json")
    parser.add_argument("--out", type=Path, required=True, help="output path without suffix")
    parser.add_argument("--scorer", choices=["v1", "v2"], default="v2", help="scorer rules")
    args = parser.parse_args()
    from analyst.evaluation import e2e_eval

    e2e_eval.SCORER_RULES = args.scorer
    rows = {}
    for item in args.rows:
        name, path = item.split("=", 1)
        rows[name] = summarise(json.loads(Path(path).read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "set": args.set,
        "scorer_rules": args.scorer,
        "rows": rows,
        "sources": dict(r.split("=", 1) for r in args.rows),
    }
    args.out.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown(rows, args.set, args.scorer), encoding="utf-8")
    print(markdown(rows, args.set, args.scorer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
