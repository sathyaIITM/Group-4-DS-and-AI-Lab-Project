"""Part B figures of the Milestone 5 report: domain and tool decisions on dev_human (198 items).

    python scripts/m5_decision_figures.py

Reads the committed dev_human predictions of every candidate system and applies its temperature,
fitted by NLL on that system's calibration-split predictions (`domain_eval.fit_temperature`);
systems without calibration predictions (Jev and zero-shot Kev on tool) are shown raw, as in the
report. Laya figures use the predictions made on the local machine (`*_mac_*`). Temperature does not
change the predicted label, so accuracies equal the report's. Writes to docs/milestones/figures/m5/,
for each decision `<d>` in {domain, tool}:

- `confusion_<d>_dev_human.png`: confusion matrices, row-normalised, counts in the cells;
- `roc_<d>_dev_human.png` and `pr_<d>_dev_human.png`: macro-averaged one-vs-rest ROC and
  precision-recall curves;
- `auc_<d>_dev_human.json`: temperature, accuracy, macro and per-label AUROC and average precision
  (the table view of the curve figures).
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

from analyst.evaluation.domain_eval import apply_temperature, fit_temperature  # noqa: E402

PRED = ROOT / "outputs" / "predictions"
OUT = ROOT / "docs" / "milestones" / "figures" / "m5"
LABELS = {
    "domain": (
        "labour", "agriculture", "rainfall", "prices_economy", "health", "other", "multiple",
        "unspecified",
    ),
    "tool": (
        "run_sql", "search_catalog", "describe_table", "ask_clarification", "decline_not_covered",
        "explain_result", "make_chart",
    ),
}  # fmt: skip
SHORT = {
    "domain": ["lab", "agr", "rain", "price", "hlth", "oth", "mult", "unsp"],
    "tool": ["sql", "search", "desc", "clarify", "decline", "explain", "chart"],
}
# Categorical slots 1-6 of the validated palette, in fixed order, with a dash style each.
STYLE = [
    ("#2a78d6", "-"), ("#eb6834", "--"), ("#1baf7a", "-."), ("#eda100", ":"),
    ("#e87ba4", (0, (5, 2, 1, 2))), ("#008300", (0, (1, 1))),
]  # fmt: skip
# name, dev_human predictions, calibration predictions (None: raw probabilities)
SYSTEMS = {
    "domain": (
        ("Kev zero-shot", "domain_zeroshot_v2_dev_human", "domain_zeroshot_v2_calibration"),
        ("Kev ep3_s2 (v4)", "domain_ep3_s2_dev_human", "domain_ep3_s2_calibration"),
        ("Kev joint lr4e-05_s1", "domain_joint_lr4e-05_s1_dev_human",
         "domain_joint_lr4e-05_s1_calibration"),
        ("Laya domain ep6_s1", "domain_laya_dom_ep6_s1_mac_dev_human",
         "domain_laya_dom_ep6_s1_mac_calibration"),
        ("Laya joint lr5e-05_s1", "domain_laya_joint_lr5e-05_s1_mac_dev_human",
         "domain_laya_joint_lr5e-05_s1_mac_calibration"),
        ("Jev", "domain_jev_dev_human", "domain_jev_v2_calibration"),
    ),
    "tool": (
        ("Kev zero-shot", "tool_zeroshot_v2_dev_human", None),
        ("Kev joint lr4e-05_s1", "tool_joint_lr4e-05_s1_dev_human",
         "tool_joint_lr4e-05_s1_calibration"),
        ("Laya joint lr5e-05_s1", "tool_laya_joint_lr5e-05_s1_mac_dev_human",
         "tool_laya_joint_lr5e-05_s1_mac_calibration"),
        ("Jev", "tool_jev_dev_human", None),
    ),
}  # fmt: skip
INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6b68", "#e4e4e1", "#fcfcfb"
BLUES = LinearSegmentedColormap.from_list("blues", ["#fcfcfb", "#cde2fb", "#6da7ec", "#1c5cab"])


def _matrix(name: str, labels: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    rows = [json.loads(x) for x in (PRED / f"{name}.jsonl").read_text().splitlines() if x]
    truth = np.array([labels.index(r["label"]) for r in rows])
    probs = np.array([[float(r["probabilities"].get(k, 0.0)) for k in labels] for r in rows])
    return truth, probs


def load(decision: str) -> dict[str, tuple[np.ndarray, np.ndarray, float | None]]:
    """Labels, (calibrated) probabilities and temperature of every system of a decision."""
    labels = LABELS[decision]
    data = {}
    for name, dev, cal in SYSTEMS[decision]:
        truth, raw = _matrix(dev, labels)
        temperature = None
        if cal is not None:
            cal_truth, cal_raw = _matrix(cal, labels)
            temperature = float(fit_temperature(cal_raw, cal_truth))
            raw = apply_temperature(raw, temperature)
        data[name] = (truth, raw, temperature)
    return data


def style(ax: plt.Axes) -> None:
    """Recessive axes and grid."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(color=GRID, linewidth=0.6)


def confusion(decision: str, data: dict) -> None:
    """Row-normalised confusion matrices as small multiples."""
    n = len(LABELS[decision])
    cols = 3 if len(data) > 4 else 2
    rows = (len(data) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(5.4 * cols, 5 * rows), facecolor=SURFACE)
    for ax in axes.flat[len(data) :]:
        ax.set_visible(False)
    for ax, (name, (truth, probs, _)) in zip(axes.flat, data.items(), strict=False):
        predicted = probs.argmax(axis=1)
        counts = np.zeros((n, n), dtype=int)
        for t, p in zip(truth, predicted, strict=True):
            counts[t, p] += 1
        rates = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
        ax.imshow(rates, cmap=BLUES, vmin=0, vmax=1)
        for i in range(n):
            for j in range(n):
                if counts[i, j]:
                    ink = "#ffffff" if rates[i, j] > 0.6 else INK
                    ax.text(j, i, counts[i, j], ha="center", va="center", fontsize=8, color=ink)
        accuracy = (predicted == truth).mean()
        ax.set_title(f"{name}: accuracy {accuracy:.3f}", fontsize=10, color=INK, loc="left")
        ax.set_xticks(range(n), SHORT[decision], fontsize=8, color=MUTED, rotation=45)
        ax.set_yticks(range(n), SHORT[decision], fontsize=8, color=MUTED)
        ax.set_xlabel("predicted", fontsize=8, color=MUTED)
        ax.set_ylabel("human label", fontsize=8, color=MUTED)
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.suptitle(
        f"{decision.capitalize()} decision on dev_human (198 items): counts, shaded by row share",
        fontsize=11, color=INK, x=0.04, ha="left",
    )  # fmt: skip
    fig.tight_layout()
    fig.savefig(OUT / f"confusion_{decision}_dev_human.png", dpi=150, metadata={"Software": None})
    plt.close(fig)


def curves(decision: str, data: dict) -> dict:
    """Macro one-vs-rest ROC and PR curves; returns the table view."""
    grid = np.linspace(0, 1, 201)
    table: dict[str, dict] = {}
    figs = {kind: plt.subplots(figsize=(7, 6), facecolor=SURFACE) for kind in ("roc", "pr")}
    for (name, (truth, probs, temperature)), (colour, dash) in zip(
        data.items(), STYLE, strict=False
    ):
        tprs, precisions, per_label = [], [], {}
        for k, label in enumerate(LABELS[decision]):
            positive = (truth == k).astype(int)
            if positive.sum() in (0, len(positive)):
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
            "temperature": None if temperature is None else round(temperature, 4),
            "accuracy": round(float((probs.argmax(axis=1) == truth).mean()), 4),
            "macro_auroc": round(macro_auroc, 4),
            "macro_average_precision": round(macro_ap, 4),
            "per_label": per_label,
        }
        for kind, curve, value in (
            ("roc", np.mean(tprs, axis=0), macro_auroc),
            ("pr", np.mean(precisions, axis=0), macro_ap),
        ):
            figs[kind][1].plot(
                grid, curve, color=colour, linestyle=dash, linewidth=2,
                label=f"{name} ({value:.4f})",
            )  # fmt: skip
    for kind, (fig, ax) in figs.items():
        style(ax)
        if kind == "roc":
            ax.plot([0, 1], [0, 1], color=GRID, linewidth=1)
            ax.set_xlabel("false positive rate", fontsize=9, color=MUTED)
            ax.set_ylabel("true positive rate", fontsize=9, color=MUTED)
            title = f"{decision.capitalize()} on dev_human: macro one-vs-rest ROC (AUROC)"
        else:
            ax.set_xlabel("recall", fontsize=9, color=MUTED)
            ax.set_ylabel("precision", fontsize=9, color=MUTED)
            title = f"{decision.capitalize()} on dev_human: macro precision-recall (avg. precision)"
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.legend(
            frameon=False, fontsize=8, labelcolor=INK,
            loc="lower right" if kind == "roc" else "lower left",
        )  # fmt: skip
        fig.tight_layout()
        fig.savefig(OUT / f"{kind}_{decision}_dev_human.png", dpi=160, metadata={"Software": None})
        plt.close(fig)
    return table


def main() -> None:
    """Write the figures and tables of both decisions."""
    OUT.mkdir(parents=True, exist_ok=True)
    for decision in ("domain", "tool"):
        data = load(decision)
        confusion(decision, data)
        table = curves(decision, data)
        note = (
            "Temperatures fitted by NLL on each system's calibration-split predictions; "
            "systems without them are raw. Laya: predictions from the local machine."
        )
        (OUT / f"auc_{decision}_dev_human.json").write_text(
            json.dumps({"note": note, "systems": table}, indent=2) + "\n", encoding="utf-8"
        )
        for name, row in table.items():
            print(
                f"{decision} | {name}: accuracy {row['accuracy']}, macro AUROC "
                f"{row['macro_auroc']}, macro AP {row['macro_average_precision']}, "
                f"T {row['temperature']}"
            )
    print("written to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
