"""Catalogue and metadata checklist (T1 brief Section 5.1) as a Markdown report.

    python scripts/check_catalogue.py [--samples 5] [--out docs/specs/catalogue_check.md]

For every table in data/processed/catalogue.json: title, domain, period types and conventions,
indicator units, geography levels and total rows, coverage, and flag counts. Then a sample of
published values is traced back to its cell in the raw file through the lineage columns
(`source_row`, and the period or indicator column the value came from): the published value
must equal the raw cell after the documented cleaning. The judgements the checklist asks for
(whether a title or caveat reads clearly, whether a convention matches the publisher) stay with
the reviewer; the report gives the facts to judge.
"""

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
SOURCES = ROOT / "configs" / "sources"


def number(text: Any) -> float | None:
    """Read a number from text, ignoring other characters."""
    cleaned = re.sub(r"[^0-9.\-]", "", str(text))
    try:
        return float(cleaned)
    except ValueError:
        return None


def trace(table: dict[str, Any], samples: int, rng: random.Random) -> list[dict[str, Any]]:
    """Published values against the raw cell they came from."""
    import tomllib

    config = tomllib.loads((SOURCES / f"{table['dataset_id']}.toml").read_text())
    raw_path = RAW / config["dataset"]["raw_file"]
    if not raw_path.exists():
        return [{"note": f"raw file {raw_path.name} not present"}]
    from analyst.data.ops import clean_frame

    raw, _ = clean_frame(pd.read_csv(raw_path, dtype=str, keep_default_na=False))
    obs = duckdb.sql(
        f"SELECT * FROM read_parquet('{PROCESSED / (table['obs_table'] + '.parquet')}') "  # noqa: S608
        "WHERE value IS NOT NULL"
    ).df()
    header_of = {spec["id"]: header for header, spec in config["values"].get("columns", {}).items()}
    rows = []
    for _, observation in obs.sample(
        min(samples, len(obs)), random_state=rng.randint(0, 10**6)
    ).iterrows():
        if config["values"]["mode"] == "periods":
            source_column = observation.get("period_source")
        else:
            source_column = header_of.get(
                observation["indicator_id"], observation.get("indicator_label_source")
            )
        cell = None
        if source_column in raw.columns and 0 <= int(observation["source_row"]) < len(raw):
            cell = raw.iloc[int(observation["source_row"])][source_column]
        raw_number = number(cell) if cell is not None else None
        rows.append(
            {
                "place": observation["geo_name"],
                "period": observation["period_label"],
                "indicator": observation["indicator_id"],
                "published": observation["value"],
                "raw_cell": cell,
                "match": raw_number is not None
                and abs(
                    (
                        abs(raw_number)
                        if observation["quality_flag"] == "low_sample_estimate"
                        else raw_number
                    )
                    - float(observation["value"])
                )
                < 1e-6,
            }
        )
    return rows


def main() -> None:
    """Write the catalogue and metadata checklist."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    rng = random.Random(args.seed)  # noqa: S311 - reproducible sampling, not security
    catalogue = json.loads((PROCESSED / "catalogue.json").read_text())
    lines = [
        "# Catalogue check",
        "",
        f"Produced by `scripts/check_catalogue.py --samples {args.samples} --seed {args.seed}`"
        f" from `data/processed/catalogue.json` (contract {catalogue['contract_version']}).",
        "",
        "| Table | Domain | Periods | Start month | Geography | Total rows | Coverage | Units "
        "| Flags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    traced_all = []
    for table in catalogue["tables"]:
        flags = ", ".join(f"{k} {v:,}" for k, v in sorted(table["flag_counts"].items()))
        units = sorted(set(table["indicator_units"].values()))
        units_text = ", ".join(units[:4]) + (f" (+{len(units) - 4})" if len(units) > 4 else "")
        lines.append(
            f"| `{table['dataset_id']}` | {table['domain']} | {', '.join(table['period_types'])} | "
            f"{table.get('period_start_month') or '-'} | {', '.join(table['geo_levels'])} | "
            f"{'yes' if table['has_total_rows'] else 'no'} | {table['coverage_start']} to "
            f"{table['coverage_end']} | {units_text} | {flags} |"
        )
        traced_all.append((table["dataset_id"], trace(table, args.samples, rng)))
    lines += ["", "## Values traced to the raw file", ""]
    total = matched = 0
    for dataset_id, rows in traced_all:
        lines += [
            f"### `{dataset_id}`",
            "",
            "| Place | Period | Indicator | Published | Raw cell | Match |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            if "note" in row:
                lines.append(f"| {row['note']} | | | | | |")
                continue
            total += 1
            matched += row["match"]
            lines.append(
                f"| {row['place']} | {row['period']} | `{row['indicator']}` | {row['published']} | "
                f"{row['raw_cell']} | {'yes' if row['match'] else '**no**'} |"
            )
        lines.append("")
    lines.insert(4, f"Traced values matching the raw file: {matched} of {total}.")
    lines.insert(5, "")
    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
