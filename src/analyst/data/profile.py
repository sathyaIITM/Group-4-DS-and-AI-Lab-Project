"""Profiles of a published table and the comparison of a new one with the approved one.

The approved profile is stored with the configuration. Each refresh is compared with
it: a jump by about a power of ten suggests a unit change and blocks the table; a
smaller shift in the middle or tails of an indicator, or a large change in row count,
is shown to a person as a warning.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analyst.data.contract import ReviewItem

PROFILES_DIR = Path("configs/profiles")
UNIT_SHIFT_RATIO = 9.0  # a median moving by this factor looks like a change of unit
SHIFT_MADS = 3.0  # robust z-score threshold for a distribution shift (starting value)
ROW_CHANGE = 0.20  # relative change in observation count worth a person's attention


def profile_obs(obs: pd.DataFrame) -> dict[str, Any]:
    """Row count and per-indicator median and 5th/95th percentiles of non-empty values."""
    indicators: dict[str, dict[str, float]] = {}
    for indicator_id, group in obs.groupby("indicator_id"):
        values = group["value"].dropna().to_numpy()
        if len(values) == 0:
            continue
        indicators[str(indicator_id)] = {
            "median": float(np.median(values)),
            "mad": float(np.median(np.abs(values - np.median(values)))),
            "p05": float(np.percentile(values, 5)),
            "p95": float(np.percentile(values, 95)),
        }
    return {"observations": len(obs), "indicators": indicators}


def compare_profiles(
    dataset_id: str, approved: dict[str, Any], current: dict[str, Any]
) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    for indicator_id, now in current["indicators"].items():
        before = approved["indicators"].get(indicator_id)
        if before is None:
            continue
        old, new = before["median"], now["median"]
        if old > 0 and new > 0 and (new / old >= UNIT_SHIFT_RATIO or old / new >= UNIT_SHIFT_RATIO):
            items.append(
                ReviewItem(
                    dataset_id=dataset_id,
                    severity="block",
                    kind="unit_change_suspected",
                    detail=f"median of {indicator_id} moved from {old:g} to {new:g}",
                    count=1,
                    suggestion="check the unit or scale in the source; set it in the configuration",
                )
            )
            continue
        spread = max(before["mad"], 1e-9)
        if abs(new - old) / (1.4826 * spread) > SHIFT_MADS and abs(new - old) > 0:
            items.append(
                ReviewItem(
                    dataset_id=dataset_id,
                    severity="warn",
                    kind="distribution_shift",
                    detail=f"median of {indicator_id} moved from {old:g} to {new:g}",
                    count=1,
                    suggestion="confirm the new values are right; no configuration change needed",
                )
            )
    old_rows, new_rows = approved["observations"], current["observations"]
    if old_rows and abs(new_rows - old_rows) / old_rows > ROW_CHANGE:
        items.append(
            ReviewItem(
                dataset_id=dataset_id,
                severity="warn",
                kind="volume_change",
                detail=f"observations changed from {old_rows} to {new_rows}",
                count=abs(new_rows - old_rows),
                suggestion="confirm the source was meant to grow or shrink",
            )
        )
    return items


def load_approved(
    dataset_id: str, directory: Path = PROFILES_DIR
) -> tuple[list[str] | None, dict[str, Any] | None]:
    columns_path = directory / f"{dataset_id}.columns.json"
    profile_path = directory / f"{dataset_id}.profile.json"
    columns = json.loads(columns_path.read_text()) if columns_path.exists() else None
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else None
    return columns, profile


def save_approved(
    dataset_id: str, columns: list[str], profile: dict[str, Any], directory: Path = PROFILES_DIR
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{dataset_id}.columns.json").write_text(
        json.dumps(columns, indent=2, ensure_ascii=False) + "\n"
    )
    (directory / f"{dataset_id}.profile.json").write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n"
    )
