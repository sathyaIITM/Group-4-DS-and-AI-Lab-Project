"""Training-loss curves of the served Kev checkpoints (Milestone 5 report, Appendix C).

    python scripts/m5_loss_curves.py

Reads the committed training logs `outputs/reports/kev_runs/<run>/train.log` (one line every 10
optimiser steps: `ep<e> step <s>/<n> loss <x> ...`, s counted over all epochs) and plots the
training loss against the step, smoothed with a moving average over 5 logged points, for the three
seeds of the `ep3` recipe (domain decision) and the served joint checkpoint. Writes
`docs/milestones/figures/m5/loss_curves_kev.png`.
"""

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUNS = (  # run, label, colour (categorical slots in fixed order), dash style
    ("ep3", "ep3, seed 0 (domain)", "#2a78d6", "-"),
    ("ep3_s1", "ep3, seed 1 (domain)", "#eb6834", "--"),
    ("ep3_s2", "ep3, seed 2 (domain, served in v4)", "#1baf7a", "-."),
    ("joint_lr4e-05_s1", "joint lr4e-05, seed 1 (tool and domain)", "#eda100", ":"),
)
LINE = re.compile(r"^ep(\d+) step (\d+)/(\d+) loss ([0-9.]+)")
INK, MUTED, GRID = "#1f1f1e", "#6b6b68", "#e4e4e1"


def read(run: str) -> tuple[np.ndarray, np.ndarray]:
    """Global step and loss of one run."""
    steps, losses = [], []
    text = (ROOT / "outputs" / "reports" / "kev_runs" / run / "train.log").read_text()
    for line in text.splitlines():
        match = LINE.match(line.strip())
        if match:
            _, step, _, loss = match.groups()  # the step count is global (n = all steps)
            steps.append(int(step))
            losses.append(float(loss))
    return np.array(steps), np.array(losses)


def main() -> None:
    """Plot the curves."""
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=160)
    for run, label, colour, dash in RUNS:
        steps, losses = read(run)
        smooth = np.convolve(losses, np.ones(5) / 5, mode="valid")
        ax.plot(steps[4:], smooth, color=colour, linestyle=dash, linewidth=2, label=label)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.grid(color=GRID, linewidth=0.6)
    ax.set_xlabel("optimiser step", color=MUTED)
    ax.set_ylabel("training loss (moving average of 5 logs)", color=MUTED)
    ax.set_title("Kev-0.8B training loss, served checkpoints", color=INK, loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    out = ROOT / "docs" / "milestones" / "figures" / "m5" / "loss_curves_kev.png"
    fig.savefig(out, metadata={"Software": None})
    print("written", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
