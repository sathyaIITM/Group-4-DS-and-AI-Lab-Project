"""Mutation sweep: change the real raw files the way public data really changes.

Every mutant is released against the live release and the reaction is recorded:

    BLOCKED  not published
    WARNED   published, with a warning that names the change
    INFO     published, with information only (for example exact duplicates removed)
    SILENT   published with nothing new to read; for a harmful change this is a failure

    python scripts/robustness_sweep.py

Needs the raw files in data/raw and a release in data/processed (run
`python scripts/run_pipeline.py` first). Nothing is written to data/processed.
"""

import os
import sys
import tempfile
from collections.abc import Callable, Collection
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst.data import ops  # noqa: E402
from analyst.data.config import SourceConfig, load_all  # noqa: E402
from analyst.data.engine import RunResult, value_columns  # noqa: E402
from analyst.data.publish import run_with_baseline  # noqa: E402

RAW = Path("data/raw")
RNG = np.random.default_rng(2026)
Mutant = tuple[pd.DataFrame, SourceConfig] | None
Mutation = Callable[[pd.DataFrame, SourceConfig], Mutant]


def load(config: SourceConfig) -> pd.DataFrame:
    raw = pd.read_csv(RAW / config.dataset.raw_file, dtype="string", keep_default_na=False)
    return ops.clean_frame(raw)[0]


def value_headers(config: SourceConfig, frame: pd.DataFrame) -> list[str]:
    return [column.header for column in value_columns(config, frame)]


def place_header(config: SourceConfig) -> str | None:
    return next(
        (h for h, role in config.columns.items() if role in ("geo_state", "geo_subdivision")), None
    )


def as_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.str.replace(",", "", regex=False), errors="coerce").astype(
        "float64"
    )


def replace_numbers(out: pd.DataFrame, header: str, changed: pd.Series) -> None:
    """Write changed numbers back as text; cells that were not numbers stay as they were."""
    number = as_number(out[header])
    text = changed.round(3).astype(str)
    out[header] = pd.Series(
        np.where(number.notna(), text, out[header].astype(object)), index=out.index, dtype="string"
    )


def shuffle(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    return frame.sample(frac=1, random_state=1).reset_index(drop=True), config


def upper_case_places(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    header = place_header(config)
    if header is None:
        return None
    out = frame.copy()
    out[header] = out[header].str.upper()
    return out, config


def append_duplicate(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    return pd.concat([frame, frame.iloc[[len(frame) // 2]]], ignore_index=True), config


def drop_value_column(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    return frame.drop(columns=[value_headers(config, frame)[-1]]), config


def add_column(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    return frame.assign(brand_new_breakdown="x"), config


def misspell_place(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    header = place_header(config)
    if header is None:
        return None
    out = frame.copy()
    first = out[header].iloc[0]
    out[header] = out[header].where(out[header] != first, first + "x")
    return out, config


def inject_token(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    out = frame.copy()
    out.loc[out.index[len(out) // 3], value_headers(config, frame)[0]] = "N/A"
    return out, config


def negative_value(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    out = frame.copy()
    headers = value_headers(config, frame)
    out.loc[out.index[len(out) // 2], headers[min(2, len(headers) - 1)]] = "-7"
    return out, config


def rescale_one_indicator(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    out = frame.copy()
    header = value_headers(config, frame)[0]
    replace_numbers(out, header, as_number(out[header]) * 100)
    return out, config


def noise_in_a_third(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    out = frame.copy()
    for header in value_headers(config, frame):
        number = as_number(out[header])
        pick = RNG.random(len(out)) < 0.30
        replace_numbers(out, header, number.where(~pick, number * 1.05))
    return out, config


def truncate_history(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    return frame.iloc[: len(frame) // 2].copy(), config


def move_year_window(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    if config.period.type != "survey_year":
        return None
    moved = config.model_copy(deep=True)
    moved.period.start_month = 4
    return frame, moved


def swap_two_columns(frame: pd.DataFrame, config: SourceConfig) -> Mutant:
    headers = value_headers(config, frame)
    if len(headers) < 2:
        return None
    out = frame.copy()
    out[headers[0]], out[headers[1]] = frame[headers[1]].copy(), frame[headers[0]].copy()
    return out, config


MUTATIONS: list[tuple[str, bool, Mutation]] = [
    ("row order shuffled", False, shuffle),
    ("place names upper-cased", False, upper_case_places),
    ("one exact duplicate row appended", True, append_duplicate),
    ("last value column dropped", True, drop_value_column),
    ("unannounced new column", True, add_column),
    ("one place misspelt", True, misspell_place),
    ("one cell becomes 'N/A'", True, inject_token),
    ("one value becomes -7", True, negative_value),
    ("one indicator rescaled x100", True, rescale_one_indicator),
    ("30% of values +5%", True, noise_in_a_third),
    ("history cut to the first half", True, truncate_history),
    ("year window moved July to April (config)", True, move_year_window),
    ("two value columns swapped", True, swap_two_columns),
]


def classify(result: RunResult, baseline: Collection[tuple[str, str]]) -> tuple[str, str]:
    new = [i for i in result.review if (i.kind, i.severity) not in baseline]
    blocks = sorted({i.kind for i in new if i.severity == "block"})
    if result.blocked:
        return "BLOCKED", ",".join(blocks or ["(block already in the baseline)"])
    for severity, label in (("warn", "WARNED"), ("info", "INFO")):
        kinds = sorted({i.kind for i in new if i.severity == severity})
        if kinds:
            return label, ",".join(kinds)
    return "SILENT", ""


def release(config: SourceConfig, frame: pd.DataFrame) -> RunResult:
    with tempfile.TemporaryDirectory() as directory:
        frame.to_csv(Path(directory) / config.dataset.raw_file, index=False)
        return run_with_baseline(config, Path(directory))


def main() -> int:
    os.chdir(ROOT)
    rows = []
    for config in load_all():
        frame = load(config)
        baseline = {(i.kind, i.severity) for i in release(config, frame).review}
        for name, does_harm, mutate in MUTATIONS:
            made = mutate(frame, config)
            if made is None:
                continue
            mutated, changed_config = made
            outcome, detail = classify(release(changed_config, mutated), baseline)
            rows.append((config.dataset_id, name, does_harm, outcome, detail))
    table = pd.DataFrame(rows, columns=["dataset", "change", "harmful", "outcome", "detail"])
    with pd.option_context("display.width", 250, "display.max_colwidth", 70):
        print(table.to_string(index=False))
    is_harmful = table["harmful"].to_numpy(dtype=bool)
    harmful, harmless = table[is_harmful], table[~is_harmful]
    print(
        f"\nharmful changes: {len(harmful)}; outcomes {harmful['outcome'].value_counts().to_dict()}"
    )
    blocked_harmless = int((harmless["outcome"] == "BLOCKED").sum())
    print(f"harmless changes: {len(harmless)}; blocked {blocked_harmless}")
    silent = int((harmful["outcome"] == "SILENT").sum())
    return 1 if silent or blocked_harmless else 0


if __name__ == "__main__":
    raise SystemExit(main())
