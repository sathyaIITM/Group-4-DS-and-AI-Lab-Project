"""Exploratory data analysis for the Milestone 2 tables and label sets.

Reads the processed Parquet tables, the routing splits and the text-to-SQL
ground truth, then writes figures and a Markdown summary to
docs/figures/milestone2/. Run from any directory:

    python scripts/eda_tables.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
SPLITS_DIR = ROOT_DIR / "data" / "splits" / "kev"
GROUND_TRUTH = ROOT_DIR / "data" / "ground_truths" / "text_to_sql_ground_truth_100.csv"
OUT_DIR = ROOT_DIR / "docs" / "figures" / "milestone2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TABLES = {
    "imd_subdivision_monthly_rainfall": ["subdivision", "year"],
    "plfs_state_ur_usual_status": ["state_ut"],
    "nfhs5_district_indicators": ["state_name", "district_name", "indicator_id"],
    "mandi_daily_prices": [
        "state_name",
        "district_name",
        "market_name",
        "commodity_name",
        "variety",
        "grade",
        "arrival_date",
    ],
    "ncrb_annual_crime_statistics": ["year"],
}

lines: list[str] = ["# Milestone 2 EDA summary", "", "Produced by `scripts/eda_tables.py`.", ""]


def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT_DIR / name, dpi=130, metadata={"Software": None})
    plt.close(fig)


def iqr_outliers(series: pd.Series) -> int:
    values = series.dropna()
    if values.empty:
        return 0
    q1, q3 = values.quantile([0.25, 0.75])
    spread = q3 - q1
    return int(((values < q1 - 1.5 * spread) | (values > q3 + 1.5 * spread)).sum())


# -------------------------------------------------------------------
# 1. Table profiles: size, missing values, duplicates, outliers
# -------------------------------------------------------------------
frames: dict[str, pd.DataFrame] = {}
lines += [
    "## Table profiles",
    "",
    "| Table | Rows | Columns | Missing cells | Exact duplicate rows | Duplicate keys |",
    "| --- | --- | --- | --- | --- | --- |",
]
for table, key in TABLES.items():
    path = PROCESSED_DIR / f"{table}.parquet"
    if not path.exists():
        lines.append(f"| `{table}` | not built | | | | |")
        continue
    frame = pd.read_parquet(path)
    frames[table] = frame
    lines.append(
        f"| `{table}` | {len(frame):,} | {frame.shape[1]} | {int(frame.isna().sum().sum()):,} "
        f"| {int(frame.duplicated().sum()):,} | {int(frame.duplicated(subset=key).sum()):,} |"
    )

lines += ["", "## Numeric columns (count, mean, std, min, median, max, IQR outliers)", ""]
for table, frame in frames.items():
    numeric = frame.select_dtypes("number")
    if numeric.empty:
        continue
    lines += [
        f"### `{table}`",
        "",
        "| Column | Count | Mean | Std | Min | Median | Max | IQR outliers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for column in numeric.columns:
        s = numeric[column]
        lines.append(
            f"| {column} | {int(s.count()):,} | {s.mean():.2f} | {s.std():.2f} | {s.min():.2f} "
            f"| {s.median():.2f} | {s.max():.2f} | {iqr_outliers(s):,} |"
        )
    lines.append("")

lines += ["## Missing values per column (non-zero only)", ""]
for table, frame in frames.items():
    missing = frame.isna().sum()
    missing = missing[missing > 0]
    if missing.empty:
        lines.append(f"- `{table}`: none")
    else:
        detail = ", ".join(f"{c} {n:,} ({n / len(frame):.1%})" for c, n in missing.items())
        lines.append(f"- `{table}`: {detail}")
lines.append("")

# -------------------------------------------------------------------
# 2. Figures per table
# -------------------------------------------------------------------
if "imd_subdivision_monthly_rainfall" in frames:
    imd = frames["imd_subdivision_monthly_rainfall"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(imd["annual"].dropna(), bins=40, color="#3b6ea5")
    axes[0].set(title="IMD annual rainfall per sub-division-year", xlabel="mm", ylabel="count")
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    axes[1].boxplot([imd[m].dropna() for m in months], showfliers=False)
    axes[1].set_xticks(range(1, 13), [m.title() for m in months])
    axes[1].set(title="Monthly rainfall distribution (outliers hidden)", ylabel="mm")
    save(fig, "imd_rainfall.png")

if "plfs_state_ur_usual_status" in frames:
    plfs = frames["plfs_state_ur_usual_status"].set_index("state_ut")["fy_2021_22"].sort_values()
    fig, ax = plt.subplots(figsize=(7, 8))
    ax.barh(plfs.index, plfs.values, color="#3b6ea5")
    ax.set(title="PLFS unemployment rate 2021-22, usual status", xlabel="percent")
    ax.tick_params(axis="y", labelsize=7)
    save(fig, "plfs_unemployment.png")

if "nfhs5_district_indicators" in frames:
    nfhs = frames["nfhs5_district_indicators"]
    lines += ["## NFHS-5 quality flags", ""]
    for flag, n in nfhs["quality_flag"].value_counts().items():
        lines.append(f"- {flag}: {n:,} ({n / len(nfhs):.1%})")
    lines.append(f"- distinct indicators: {nfhs['indicator_id'].nunique()}")
    lines.append(
        f"- distinct (state, district) pairs: {len(nfhs[['state_name', 'district_name']].drop_duplicates())}"
    )
    lines.append("")
    wide = nfhs[nfhs["unit"] == "percent"].pivot_table(
        index=["state_name", "district_name"], columns="indicator_label", values="value"
    )
    picks = [
        c
        for c in wide.columns
        if any(
            k in c
            for k in [
                "electricity",
                "improved sanitation",
                "clean fuel",
                "women (age 15-49) who are literate",
                "with 10 or more years",
                "stunted",
                "anaemic (<12.0",
                "institutional births",
            ]
        )
    ][:8]
    if len(picks) >= 3:
        corr = wide[picks].corr()
        short = [
            p.split("(")[0][:28] if not p.lower().startswith("women") else p[:34] for p in picks
        ]
        fig, ax = plt.subplots(figsize=(8, 6.5))
        im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(picks)), short, rotation=60, ha="right", fontsize=7)
        ax.set_yticks(range(len(picks)), short, fontsize=7)
        for i in range(len(picks)):
            for j in range(len(picks)):
                ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=6)
        fig.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title("NFHS-5 district indicators: Pearson correlation")
        save(fig, "nfhs_correlation.png")
        lines += [
            "NFHS-5 correlation matrix computed over "
            f"{len(wide):,} districts for {len(picks)} indicators (figure `nfhs_correlation.png`).",
            "",
        ]

if "mandi_daily_prices" in frames:
    mandi = frames["mandi_daily_prices"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(
        np.log10(mandi["modal_price_inr_per_quintal"].clip(lower=1)), bins=50, color="#3b6ea5"
    )
    axes[0].set(
        title="Mandi modal price (log10 INR per quintal)", xlabel="log10 price", ylabel="rows"
    )
    top = mandi["commodity_name"].value_counts().head(12)[::-1]
    axes[1].barh(top.index, top.values, color="#3b6ea5")
    axes[1].set(title="Most frequent commodities", xlabel="rows")
    save(fig, "mandi_prices.png")
    lines += [
        "## Mandi snapshot",
        "",
        f"- arrival dates: {mandi['arrival_date'].min():%Y-%m-%d} to {mandi['arrival_date'].max():%Y-%m-%d}",
        f"- states {mandi['state_name'].nunique()}, markets {mandi['market_name'].nunique():,}, "
        f"commodities {mandi['commodity_name'].nunique()}",
        f"- rows where min = modal = max price: {int((mandi['min_price_inr_per_quintal'] == mandi['max_price_inr_per_quintal']).sum()):,}",
        "",
    ]

# -------------------------------------------------------------------
# 3. Class distributions: routing splits and text-to-SQL ground truth
# -------------------------------------------------------------------
split_counts: dict[str, dict[str, Counter]] = {}
for split in ["train", "calibration", "dev_synthetic"]:
    path = SPLITS_DIR / f"{split}.v1.jsonl"
    if not path.exists():
        continue
    counts: dict[str, Counter] = {"tool": Counter(), "domain": Counter()}
    for line in path.open(encoding="utf-8"):
        record = json.loads(line)
        for name in counts:
            if name in record["questions"]:
                counts[name][record["questions"][name]["label"]] += 1
    split_counts[split] = counts

if split_counts:
    lines += ["## Routing label distribution", ""]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for ax, name in zip(axes, ["tool", "domain"]):
        options = sorted({o for c in split_counts.values() for o in c[name]})
        width = 0.8 / len(split_counts)
        lines += [
            f"| `{name}` | " + " | ".join(split_counts) + " |",
            "| --- |" + " --- |" * len(split_counts),
        ]
        for option in options:
            lines.append(
                f"| {option} | "
                + " | ".join(
                    f"{c[name][option]} ({c[name][option] / sum(c[name].values()):.1%})"
                    for c in split_counts.values()
                )
                + " |"
            )
        lines.append("")
        for k, (split, c) in enumerate(split_counts.items()):
            total = sum(c[name].values())
            ax.bar(
                np.arange(len(options)) + k * width,
                [c[name][o] / total for o in options],
                width,
                label=split,
            )
        ax.set_xticks(np.arange(len(options)) + width, options, rotation=35, ha="right", fontsize=8)
        ax.set(title=f"Routing label share: {name}", ylabel="share of split")
        ax.legend(fontsize=7)
    save(fig, "routing_labels.png")

if GROUND_TRUTH.exists():
    gold = pd.read_csv(GROUND_TRUTH)
    lines += ["## Text-to-SQL ground truth", "", f"- rows: {len(gold)}"]
    for column in ["dataset", "difficulty", "expected_action", "category"]:
        lines.append(
            f"- {column}: " + ", ".join(f"{k} {v}" for k, v in gold[column].value_counts().items())
        )
    lines.append(f"- duplicate questions: {int(gold['question'].duplicated().sum())}")
    lines.append("")

(OUT_DIR / "eda_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(
    f"Wrote {OUT_DIR / 'eda_summary.md'} and figures: {sorted(p.name for p in OUT_DIR.glob('*.png'))}"
)
