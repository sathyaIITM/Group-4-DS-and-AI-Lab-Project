"""Build the IMD rainfall and PLFS unemployment tables (compatibility entry point).

The cleaning that used to live here is now configuration: ``configs/sources/`` holds one
file per table and ``analyst.data.engine`` runs them. This function remains so that code
written for Milestone 1 keeps working.
"""

from pathlib import Path

from analyst.data import publish
from analyst.data.config import load_all

WEEK1_TABLES = ("imd_subdivision_monthly_rainfall", "plfs_state_ur_usual_status")


def build_parquet(raw_dir: Path, out_dir: Path) -> dict[str, Path]:
    """Run the two week-1 tables from raw_dir and write their Parquet files to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    entries = []
    for config in load_all():
        if config.dataset_id not in WEEK1_TABLES:
            continue
        result = publish.run_with_baseline(config, raw_dir)
        if result.blocked:
            kinds = sorted({item.kind for item in result.review if item.severity == "block"})
            msg = f"{config.dataset_id} is blocked: {kinds}; see outputs/review/"
            raise ValueError(msg)
        entries.append(publish.publish(result, out_dir=out_dir))
        paths[config.view.table] = out_dir / f"{config.view.table}.parquet"
    publish.update_catalogue(entries, out_dir)
    return paths
