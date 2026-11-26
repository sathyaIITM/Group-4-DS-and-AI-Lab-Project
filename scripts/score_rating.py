"""Blind human rating of 30 agent answers (Milestone 5): agreement and per-version means.

    python scripts/score_rating.py

Reads the two raters' files and the version key from `data/labels/rating_m5/`:
`rating_sample_T1.csv`, `rating_sample_T3.csv` (one row per answer, scales 0-2 for
interpretation, completeness and wording) and `rating_key.csv` (answer to item and version; sealed
until both files were returned). Writes `outputs/reports/rating_m5.json`: per scale, the share of
exact agreement, Cohen's kappa (linear weights, for the ordinal 0-2 scale), and the mean score per
version over both raters.
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "labels" / "rating_m5"
SCALES = ("interpretation_0_2", "completeness_0_2", "wording_0_2")
RATERS = ("T1", "T3")


def _read(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {row["rating_id"]: row for row in csv.DictReader(handle)}


def main() -> None:
    """Compute agreement and per-version means; write the report."""
    ratings = {r: _read(DIR / f"rating_sample_{r}.csv") for r in RATERS}
    key = _read(DIR / "rating_key.csv")
    ids = sorted(key)
    result: dict = {"n": len(ids), "scales": {}}
    for scale in SCALES:
        a = [int(ratings["T1"][i][scale]) for i in ids]
        b = [int(ratings["T3"][i][scale]) for i in ids]
        by_version: dict[str, list[int]] = defaultdict(list)
        for i, x, y in zip(ids, a, b, strict=True):
            by_version[key[i]["version"]] += [x, y]
        result["scales"][scale] = {
            "exact_agreement": round(sum(x == y for x, y in zip(a, b, strict=True)) / len(ids), 3),
            "kappa_linear": round(float(cohen_kappa_score(a, b, weights="linear")), 3),
            "mean_by_rater": {"T1": round(sum(a) / len(a), 3), "T3": round(sum(b) / len(b), 3)},
            "mean_by_version": {
                v: round(sum(s) / len(s), 3) for v, s in sorted(by_version.items())
            },
        }
    out = ROOT / "outputs" / "reports" / "rating_m5.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
