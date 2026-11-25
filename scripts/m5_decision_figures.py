"""Part B figures of the Milestone 5 report: the domain decision on dev_human (198 items).

    python scripts/m5_decision_figures.py

Reads the committed dev_human predictions of four systems (zero-shot Kev, fine-tuned Kev `ep3`,
Jev, fine-tuned Laya `laya_s0`) and applies each system's temperature fitted on the calibration
split (from its `outputs/reports/score_domain_*.json`). Writes to docs/milestones/figures/m5/:

- `confusion_domain_dev_human.png`: confusion matrices, row-normalised, counts in the cells;
- `roc_domain_dev_human.png` and `pr_domain_dev_human.png`: macro-averaged one-vs-rest ROC and
  precision-recall curves;
- `auc_domain_dev_human.json`: macro and per-label AUROC and average precision (the table view
  of the two curve figures).

Only the domain decision: tool predictions on dev_human are not opened before the tool labels
are re-adjudicated under labelling guide 1.1.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.evaluation.domain_eval import apply_temperature  # noqa: E402

PRED = ROOT / "outputs" / "predictions"
REPORTS = ROOT / "outputs" / "reports"
OUT = ROOT / "docs" / "milestones" / "figures" / "m5"
LABELS = (
    "labour", "agriculture", "rainfall", "prices_economy", "health", "other", "multiple",
    "unspecified",
)  # fmt: skip
# name, predictions file, report with the fitted temperature, colour (categorical slots 1-4 in
# fixed order), dash style (secondary encoding)
SYSTEMS = (
    ("Kev zero-shot", "domain_zeroshot_v2_dev_human.jsonl", "score_domain_zeroshot_v2.json",
     "#2a78d6", "-"),
    ("Kev ep3", "domain_ep3_dev_human.jsonl", "score_domain_ep3_dev_human.json", "#eb6834", "--"),
    ("Jev", "domain_jev_dev_human.jsonl", "score_domain_jev_v2.json", "#1baf7a", "-."),
    ("Laya laya_s0", "domain_laya_s0_dev_human.jsonl", "score_domain_laya_s0_dev_human.json",
     "#eda100", ":"),
)  # fmt: skip
INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6b68", "#e4e4e1", "#fcfcfb"
BLUES = LinearSegmentedColormap.from_list("blues", ["#fcfcfb", "#cde2fb", "#6da7ec", "#1c5cab"])


def load(name: str, temperature_report: str) -> tuple[np.ndarray, np.ndarray, float]:
    """Labels (index), calibrated probabilities and the temperature of one system."""
    rows = [json.loads(x) for x in (PRED / name).read_text(encoding="utf-8").splitlines() if x]
    truth = np.array([LABELS.index(r["label"]) for r in rows])
    raw = np.array([[float(r["probabilities"].get(k, 0.0)) for k in LABELS] for r in rows])
    temperature = float(
        json.loads((REPORTS / temperature_report).read_text())["fitted_temperature"]
    )
    return truth, apply_temperature(raw, temperature), temperature


def style(ax: plt.Axes) -> None:
    """Recessive axes and grid."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(color=GRID, linewidth=0.6)


def confusion(data: dict[str, tuple[np.ndarray, np.ndarray, float]]) -> None:
    """Row-normalised confusion matrices as small multiples."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 10), facecolor=SURFACE)
    short = ["lab", "agr", "rain", "price", "hlth", "oth", "mult", "unsp"]
    for ax, (name, (truth, probs, _)) in zip(axes.flat, data.items(), strict=True):
        predicted = probs.argmax(axis=1)
        counts = np.zeros((len(LABELS), len(LABELS)), dtype=int)
        for t, p in zip(truth, predicted, strict=True):
            counts[t, p] += 1
        rates = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
        ax.imshow(rates, cmap=BLUES, vmin=0, vmax=1)
        for i in range(len(LABELS)):
            for j in range(len(LABELS)):
                if counts[i, j]:
                    ink = "#ffffff" if rates[i, j] > 0.6 else INK
                    ax.text(j, i, counts[i, j], ha="center", va="center", fontsize=8, color=ink)
        accuracy = (predicted == truth).mean()
        ax.set_title(f"{name}: accuracy {accuracy:.3f}", fontsize=10, color=INK, loc="left")
        ax.set_xticks(range(len(LABELS)), short, fontsize=8, color=MUTED)
        ax.set_yticks(range(len(LABELS)), short, fontsize=8, color=MUTED)
        ax.set_xlabel("predicted", fontsize=8, color=MUTED)
        ax.set_ylabel("human label", fontsize=8, color=MUTED)
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.suptitle(
        "Domain decision on dev_human (198 items): counts, shaded by row share",
        fontsize=11, color=INK, x=0.06, ha="left",
    )  # fmt: skip
    fig.tight_layout()
    fig.savefig(OUT / "confusion_domain_dev_human.png", dpi=160, metadata={"Software": None})
    plt.close(fig)


def macro_curves(data: dict[str, tuple[np.ndarray, np.ndarray, float]]) -> dict[str, dict]:
    """Macro one-vs-rest ROC and PR curves; returns the AUC table."""
    grid = np.linspace(0, 1, 201)
    table: dict[str, dict] = {}
    figs = {kind: plt.subplots(figsize=(7, 6), facecolor=SURFACE) for kind in ("roc", "pr")}
    for (name, (truth, probs, temperature)), system in zip(data.items(), SYSTEMS, strict=True):
        colour, dash = system[3], system[4]
        tprs, precisions, per_label = [], [], {}
        for k, label in enumerate(LABELS):
            positive = (truth == k).astype(int)
            if positive.sum() == 0 or positive.sum() == len(positive):
                continue
            fpr, tpr, _ = roc_curve(positive, probs[:, k])
            tprs.append(np.interp(grid, fpr, tpr))
            precision, recall, _ = precision_recall_curve(positive, probs[:, k])
            precisions.append(np.interp(grid, recall[::-1], precision[::-1]))
            per_label[label] = {
                "auroc": round(float(roc_auc_score(positive, probs[:, k])), 4),
                "average_precision": round(
                    float(average_precision_score(positive, probs[:, k])), 4
                ),
            }
        macro_auroc = float(np.mean([v["auroc"] for v in per_label.values()]))
        macro_ap = float(np.mean([v["average_precision"] for v in per_label.values()]))
        table[name] = {
            "temperature": round(temperature, 4),
            "macro_auroc": round(macro_auroc, 4),
            "macro_average_precision": round(macro_ap, 4),
            "per_label": per_label,
        }
        for kind, curve, value in (
            ("roc", np.mean(tprs, axis=0), macro_auroc),
            ("pr", np.mean(precisions, axis=0), macro_ap),
        ):
            ax = figs[kind][1]
            ax.plot(
                grid,
                curve,
                color=colour,
                linestyle=dash,
                linewidth=2,
                label=f"{name} ({value:.4f})",
            )
    for kind, (fig, ax) in figs.items():
        style(ax)
        if kind == "roc":
            ax.plot([0, 1], [0, 1], color=GRID, linewidth=1)
            ax.set_xlabel("false positive rate", fontsize=9, color=MUTED)
            ax.set_ylabel("true positive rate", fontsize=9, color=MUTED)
            title = "Domain decision on dev_human: macro one-vs-rest ROC (AUROC in brackets)"
        else:
            ax.set_xlabel("recall", fontsize=9, color=MUTED)
            ax.set_ylabel("precision", fontsize=9, color=MUTED)
            title = "Domain decision on dev_human: macro precision-recall (average precision)"
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.legend(
            frameon=False,
            fontsize=9,
            labelcolor=INK,
            loc="lower right" if kind == "roc" else "lower left",
        )
        fig.tight_layout()
        fig.savefig(OUT / f"{kind}_domain_dev_human.png", dpi=160, metadata={"Software": None})
        plt.close(fig)
    return table


def main() -> None:
    """Write the figures and the AUC table."""
    OUT.mkdir(parents=True, exist_ok=True)
    data = {name: load(file, report) for name, file, report, _, _ in SYSTEMS}
    confusion(data)
    table = macro_curves(data)
    note = "Temperatures fitted on calibration.v2 (Laya: on top of its own internal temperature)."
    (OUT / "auc_domain_dev_human.json").write_text(
        json.dumps({"note": note, "systems": table}, indent=2) + "\n", encoding="utf-8"
    )
    for name, row in table.items():
        print(
            f"{name}: macro AUROC {row['macro_auroc']}, macro AP {row['macro_average_precision']}"
        )
    print("written to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
