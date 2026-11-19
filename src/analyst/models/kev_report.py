"""Milestone 4 records for the Kev-0.8B domain runs: data coverage, training curves, the run
comparison table and the checkpoint selection.

    # coverage of the training splits: labels, sources, families, and every catalogue table
    python -m analyst.models.kev_report coverage
    # training-loss curves (from train.log) and validation NLL against epochs (from scores)
    python -m analyst.models.kev_report curves
    # comparison table of every registered run (models/registry.json)
    python -m analyst.models.kev_report table
    # apply the selection rule of configs/train.yaml to the registered runs
    python -m analyst.models.kev_report select

Inputs: `models/registry.json` and `outputs/reports/kev_runs/<run id>/` (written by
`kev_runs register`), and the score files `outputs/reports/score_domain_<run id>.json` (written
by `decision_eval score`). Outputs go to `outputs/reports/` and `outputs/figures/`.
"""

import argparse
import csv
import json
import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from analyst.decisions.phase1 import read_jsonl
from analyst.models.kev_runs import (
    ROOT,
    RUN_RECORDS,
    full_sweep,
    load_config,
    load_registry,
    parse_train_log,
)

REPORTS = ROOT / "outputs" / "reports"
FIGURES = ROOT / "outputs" / "figures"
CATALOGUE = ROOT / "configs" / "catalogue.toml"
ROUTING_SPLITS = tuple(
    ROOT / "data" / "splits" / "kev" / f"{s}.v2.jsonl"
    for s in ("train", "calibration", "dev_synthetic")
)
B0_SEEDS = ("b0_s0", "b0_s1", "b0_s2")
CATALOGUE_LINE = re.compile(r"^(?P<rank>\d+)\. (?P<table>\w+):", re.MULTILINE)


def score_path(run_id: str) -> Path:
    """Return the path of a run's domain score report."""
    return REPORTS / f"score_domain_{run_id}.json"


# ---------------------------------------------------------------------------- coverage


def target_table(meta: dict[str, Any]) -> str | None:
    """The table a template names, when it names one (describe, table, PLFS and IMD queries)."""
    parts = str(meta.get("template_id", "")).split(".")
    if parts[0] in {"describe", "table"} and len(parts) > 1:
        return parts[1]
    return {"plfs": "plfs_state_ur_usual_status", "imd": "imd_subdivision_monthly_rainfall"}.get(
        parts[0]
    )


def split_coverage(path: Path, tables: dict[str, str]) -> dict[str, Any]:
    """Count how often each table is named and ranked first in a split."""
    records = list(read_jsonl(path))
    named: Counter[str] = Counter()
    top1: Counter[str] = Counter()
    shown: Counter[str] = Counter()
    for record in records:
        table = target_table(record["_meta"])
        if table:
            named[table] += 1
        state = record["state"]
        catalogue = state.get("catalogue", "") if isinstance(state, dict) else str(state)
        for match in CATALOGUE_LINE.finditer(catalogue):
            shown[match["table"]] += 1
            if match["rank"] == "1":
                top1[match["table"]] += 1
    n = len(records)
    domains = Counter(r["questions"]["domain"]["label"] for r in records)
    tools = Counter(r["questions"]["tool"]["label"] for r in records if "tool" in r["questions"])
    return {
        "file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "records": n,
        "domain": {k: {"n": v, "share": round(v / n, 4)} for k, v in domains.most_common()},
        "tool": dict(tools.most_common()),
        "label_source": dict(Counter(r["_meta"].get("label_source") for r in records)),
        "tables": {
            table: {
                "domain": domain,
                "named_by_template": named[table],
                "top1_candidate": top1[table],
                "shown_in_top4": shown[table],
            }
            for table, domain in tables.items()
        },
        "tables_not_named": sorted(t for t in tables if named[t] == 0),
        "tables_never_top1": sorted(t for t in tables if top1[t] == 0),
    }


def coverage(splits: tuple[Path, ...] = ROUTING_SPLITS) -> dict[str, Any]:
    """Report catalogue coverage of the routing splits."""
    catalogue = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    tables = {t["name"]: t["domain"] for t in catalogue["table"]}
    return {
        "catalogue_tables": len(tables),
        "splits": {p.name: split_coverage(p, tables) for p in splits},
    }


def coverage_markdown(result: dict[str, Any]) -> str:
    """Render the coverage report as Markdown."""
    names = list(result["splits"])
    lines = [
        "# Routing data v2: coverage of the training and validation splits",
        "",
        "Produced by `python -m analyst.models.kev_report coverage`. 'Named' counts records whose",
        "template names the table; 'top-1' counts records whose retrieved catalogue ranks it",
        "first. Paraphrased and teacher-labelled records name no template table.",
        "",
        "| Table | Domain | " + " | ".join(f"{n} named / top-1" for n in names) + " |",
        "| --- | --- | " + " | ".join("---" for _ in names) + " |",
    ]
    first = result["splits"][names[0]]["tables"]
    for table, info in first.items():
        cells = [
            f"{result['splits'][n]['tables'][table]['named_by_template']} / "
            f"{result['splits'][n]['tables'][table]['top1_candidate']}"
            for n in names
        ]
        lines.append(f"| `{table}` | {info['domain']} | " + " | ".join(cells) + " |")
    lines += ["", "| Domain label | " + " | ".join(names) + " |"]
    lines.append("| --- | " + " | ".join("---" for _ in names) + " |")
    labels = list(result["splits"][names[0]]["domain"])
    for label in labels:
        cells = []
        for n in names:
            domain_stats = result["splits"][n]["domain"].get(label, {"n": 0, "share": 0.0})
            cells.append(f"{domain_stats['n']} ({domain_stats['share']:.1%})")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- curves


def loss_points(records: Path = RUN_RECORDS) -> dict[str, list[dict[str, float]]]:
    """Return the training loss points of every recorded run."""
    out = {}
    for run_dir in sorted(p for p in records.glob("*") if (p / "train.log").exists()):
        out[run_dir.name] = parse_train_log(run_dir / "train.log")["points"]
    return out


def epoch_validation(runs: tuple[str, ...] = ("ep1", "b0_s0", "ep3")) -> list[dict[str, Any]]:
    """Validation NLL (calibration split, before scaling) and dev_synthetic NLL by epochs."""
    rows = []
    for run_id in runs:
        path = score_path(run_id)
        if not path.exists():
            continue
        score = json.loads(path.read_text())
        epochs = {"ep1": 1, "ep3": 3}.get(run_id, 2)
        rows.append(
            {
                "run_id": run_id,
                "epochs": epochs,
                "calibration_nll_raw": score.get("calibration_raw", {}).get("nll"),
                "dev_nll_raw": score["dev_raw"]["nll"],
                "dev_nll_calibrated": score["dev_calibrated"]["nll"],
                "dev_accuracy": score["dev_raw"]["accuracy"],
            }
        )
    return rows


def write_curves() -> list[Path]:
    """Write the training-loss curves as a CSV table and a figure."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written: list[Path] = []
    points = loss_points()
    REPORTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    table = REPORTS / "kev_train_loss.csv"
    with table.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_id", "epoch", "step", "steps", "loss"])
        for run_id, rows in points.items():
            for point in rows:
                writer.writerow(
                    [run_id, point["epoch"], point["step"], point["steps"], point["loss"]]
                )
    written.append(table)
    if points:
        fig, ax = plt.subplots(figsize=(7, 4))
        for run_id, rows in points.items():
            ax.plot(
                [point["step"] for point in rows], [point["loss"] for point in rows], label=run_id
            )
        ax.set_xlabel("optimizer step")
        ax.set_ylabel("training cross-entropy (mean of the last 10 steps)")
        ax.set_title("Kev-0.8B domain runs: training loss")
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = FIGURES / "kev_train_loss.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)
    rows = epoch_validation()
    out = REPORTS / "kev_validation_by_epoch.json"
    out.write_text(json.dumps(rows, indent=2) + "\n")
    written.append(out)
    if rows:
        fig, ax = plt.subplots(figsize=(5, 3.5))
        x = [r["epochs"] for r in rows]
        for key, label in (
            ("calibration_nll_raw", "calibration NLL (raw)"),
            ("dev_nll_calibrated", "dev_synthetic NLL (after T)"),
        ):
            ax.plot(x, [r[key] for r in rows], marker="o", label=label)
        ax.set_xlabel("epochs")
        ax.set_ylabel("NLL")
        ax.set_xticks(x)
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = FIGURES / "kev_validation_by_epoch.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)
    return written


# ---------------------------------------------------------------------------- table


def comparison_rows() -> list[dict[str, Any]]:
    """Return one comparison row per registered run."""
    config = load_config()
    factors = {r.run_id: r.factor for r in full_sweep(config)}
    rows = []
    for run_id, entry in sorted(load_registry().items()):
        score = json.loads(score_path(run_id).read_text()) if score_path(run_id).exists() else {}
        clipped = sum(g.get("clipped_steps", 0) for g in entry.grad_norm)
        steps = sum(g.get("steps", 0) for g in entry.grad_norm)
        raw = score.get("dev_raw", {})
        cal = score.get("dev_calibrated", {})
        rows.append(
            {
                "run_id": run_id,
                "factor": factors.get(run_id, "other"),
                "platform": entry.platform or entry.device,
                "init": "kev-0.8b" if entry.init_from else "base",
                "lr": entry.flags.get("lr"),
                "epochs": entry.flags.get("epochs"),
                "seed": entry.seed,
                "wall_min": round(entry.wall_seconds / 60, 1) if entry.wall_seconds else None,
                "peak_gb": round(entry.peak_device_bytes / 1e9, 2)
                if entry.peak_device_bytes
                else None,
                "clipped_share": round(clipped / steps, 3) if steps else None,
                "final_train_loss": entry.final_train_loss,
                "calibration_nll_raw": score.get("calibration_raw", {}).get("nll"),
                "temperature": score.get("fitted_temperature"),
                "dev_accuracy": raw.get("accuracy"),
                "dev_macro_f1": raw.get("macro_f1"),
                "dev_nll": cal.get("nll"),
                "dev_ece_raw": raw.get("ece"),
                "dev_ece_calibrated": cal.get("ece"),
            }
        )
    return rows


def _fmt(value: Any) -> str:
    """Format a value for a Markdown table."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3g}" if abs(value) < 1e-2 else f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def table_markdown(rows: list[dict[str, Any]]) -> str:
    """Render comparison rows as a Markdown table."""
    if not rows:
        return "No registered runs.\n"
    keys = list(rows[0])
    lines = [
        "# Kev-0.8B domain runs: comparison",
        "",
        "Produced by `python -m analyst.models.kev_report table` from `models/registry.json` and",
        "`outputs/reports/score_domain_<run>.json`. dev = dev_synthetic (rule and teacher",
        "labels); accuracy and macro-F1 are unchanged by temperature; dev NLL is after the",
        "temperature fitted on calibration.",
        "",
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    lines += ["| " + " | ".join(_fmt(r[k]) for k in keys) + " |" for r in rows]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------- selection


def select(rows: list[dict[str, Any]], eligible: set[str] | None = None) -> dict[str, Any]:
    """The rule in configs/train.yaml: lowest dev_synthetic NLL after temperature, macro-F1
    breaking ties; another setting replaces B0 only if its NLL is below the mean of the B0
    seeds by more than their range (max - min). Only `eligible` runs compete (by default the
    planned runs of the config), so a zero-shot, smoke or older registered run never does.
    Without three B0 seeds, no decision. A range heuristic, not a significance test."""
    if eligible is None:
        eligible = set(load_config().get("planned", {}))
    scored = [r for r in rows if r["dev_nll"] is not None and r["run_id"] in eligible]
    seeds = [r for r in scored if r["run_id"] in B0_SEEDS]
    if len(seeds) < len(B0_SEEDS):
        return {"decision": None, "reason": "fewer than three scored B0 seeds"}
    nlls = [r["dev_nll"] for r in seeds]
    b0_mean = sum(nlls) / len(nlls)
    noise = max(nlls) - min(nlls)

    def key(row: dict[str, Any]) -> tuple[float, float]:
        """Sort key: lowest dev loss, then highest dev macro-F1."""
        return (row["dev_nll"], -(row["dev_macro_f1"] or 0.0))

    others = sorted((r for r in scored if r["run_id"] not in B0_SEEDS), key=key)
    best_b0 = min(seeds, key=key)
    challenger = others[0] if others else None
    replaces = challenger is not None and challenger["dev_nll"] < b0_mean - noise
    chosen = challenger if replaces and challenger else best_b0
    return {
        "decision": chosen["run_id"],
        "b0_seed_nll": dict(zip([r["run_id"] for r in seeds], nlls, strict=True)),
        "b0_mean_nll": b0_mean,
        "noise_floor": noise,
        "best_other": challenger["run_id"] if challenger else None,
        "best_other_nll": challenger["dev_nll"] if challenger else None,
        "other_replaces_b0": replaces,
        "eligible": sorted(eligible),
        "excluded": sorted(r["run_id"] for r in rows if r["run_id"] not in eligible),
        "rule": load_config().get("selection"),
    }


# ---------------------------------------------------------------------------- CLI


def main() -> None:
    """Command-line entry point for Kev reports."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("coverage")
    sub.add_parser("curves")
    sub.add_parser("table")
    sub.add_parser("select")
    args = parser.parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)
    if args.command == "coverage":
        result = coverage()
        (REPORTS / "kev_data_coverage_v2.json").write_text(json.dumps(result, indent=2) + "\n")
        markdown = coverage_markdown(result)
        (REPORTS / "kev_data_coverage_v2.md").write_text(markdown)
        print(markdown)
    elif args.command == "curves":
        for path in write_curves():
            print("wrote", path.relative_to(ROOT))
    elif args.command == "table":
        rows = comparison_rows()
        (REPORTS / "kev_runs_table.json").write_text(json.dumps(rows, indent=2) + "\n")
        markdown = table_markdown(rows)
        (REPORTS / "kev_runs_table.md").write_text(markdown)
        print(markdown)
    else:
        result = select(comparison_rows())
        (REPORTS / "kev_selection.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
