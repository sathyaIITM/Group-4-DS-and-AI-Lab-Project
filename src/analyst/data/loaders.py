"""Convert the two week-1 raw tables to typed Parquet.

Cleaning is deliberately minimal: types are fixed and missing-value markers
become nulls, but wide layouts, name variants and aggregate rows are kept so
that the feasibility checks meet them as a user would.
"""

from pathlib import Path

import pandas as pd

RAINFALL_RAW = "imd_subdivision_monthly_rainfall"
RAINFALL_TABLE = "imd_subdivision_monthly_rainfall"
PLFS_RAW = "plfs_state_ur_usual_status_2017_22"
PLFS_TABLE = "plfs_state_ur_usual_status"

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
RAINFALL_NUMERIC = [*MONTHS, "annual", "jf", "mam", "jjas", "ond"]
PLFS_YEARS = ["2017_18", "2018_19", "2019_20", "2020_21", "2021_22"]


def clean_rainfall(raw: pd.DataFrame) -> pd.DataFrame:
    """Type the IMD sub-divisional monthly rainfall table (millimetres)."""
    frame = raw.copy()
    frame["subdivision"] = frame["subdivision"].astype("string").str.strip()
    frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype("int64")
    for column in RAINFALL_NUMERIC:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[["subdivision", "year", *RAINFALL_NUMERIC]]


def clean_plfs_ur(raw: pd.DataFrame) -> pd.DataFrame:
    """Type the PLFS state-wise unemployment rate table (percent, usual status, 15+).

    One column per survey year (fiscal-year labels, July to June); 'NA' becomes null.
    """
    frame = raw.rename(columns={"states_uts": "state_ut"}).copy()
    frame["state_ut"] = frame["state_ut"].astype("string").str.strip()
    renamed = {f"_{year}": f"fy_{year}" for year in PLFS_YEARS}
    frame = frame.rename(columns=renamed)
    for column in renamed.values():
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[["state_ut", *renamed.values()]]


def build_parquet(raw_dir: Path, out_dir: Path) -> dict[str, Path]:
    """Read the raw CSVs from raw_dir and write one Parquet file per table to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        RAINFALL_TABLE: clean_rainfall(pd.read_csv(raw_dir / f"{RAINFALL_RAW}.csv")),
        PLFS_TABLE: clean_plfs_ur(pd.read_csv(raw_dir / f"{PLFS_RAW}.csv")),
    }
    paths = {}
    for name, frame in tables.items():
        path = out_dir / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        paths[name] = path
    return paths
