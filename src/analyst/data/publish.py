"""Publication: staging, atomic replacement, catalogue, lineage and the release check.

A candidate release is built beside the live one and replaces it only when no blocking
item remains. The catalogue is recomputed from the published data; ``verify_release``
re-derives every catalogue fact from the files on disk and compares.
"""

import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from analyst.data import profile as profile_mod
from analyst.data import reconcile
from analyst.data.config import SourceConfig, load_all
from analyst.data.contract import CONTRACT_VERSION, CatalogueEntry, ReviewItem
from analyst.data.engine import RunResult, run_source
from analyst.data.validate import category_columns
from analyst.data.views import build_agent_view

PROCESSED = Path("data/processed")
REVIEW_DIR = Path("outputs/review")
LINEAGE_DIR = Path("outputs/lineage")
CATALOGUE = "catalogue.json"


def build_dim_period(start: str = "1901-01-01", end: str = "2030-12-31") -> pd.DataFrame:
    """One row per day: calendar, fiscal (April-March) and July-June year."""
    days = pd.date_range(start, end, freq="D")
    month = days.month
    year = days.year

    def span(first_year: pd.Series) -> pd.Series:
        return first_year.astype(str) + "-" + ((first_year + 1) % 100).astype(str).str.zfill(2)

    frame = pd.DataFrame({"date": days, "calendar_year": year, "month": month})
    frame["quarter"] = days.quarter
    frame["fiscal_year"] = span(pd.Series(year - (month < 4), index=frame.index))
    frame["jul_jun_year"] = span(pd.Series(year - (month < 7), index=frame.index))
    return frame


def build_catalogue_entry(
    config: SourceConfig, obs: pd.DataFrame, raw_sha256: str
) -> CatalogueEntry:
    """Facts about one table, computed from its observation rows only."""
    dataset = config.dataset
    categories = {name: int(obs[name].nunique()) for name in category_columns(config)}
    units = obs.drop_duplicates("indicator_id").set_index("indicator_id")["unit"].to_dict()
    return CatalogueEntry(
        dataset_id=dataset.id,
        dataset_version=str(obs["dataset_version"].iloc[0]),
        config_version=dataset.config_version,
        domain=dataset.domain,
        title=dataset.title,
        source_name=dataset.source_name,
        source_table=dataset.source_table,
        publisher=dataset.publisher,
        licence=dataset.licence,
        retrieved=dataset.retrieved,
        raw_sha256=raw_sha256,
        obs_table=config.obs_table,
        agent_table=config.view.table,
        rows=len(obs),
        geo_levels=sorted(obs["geo_level"].unique()),
        geo_vintage=config.geo.vintage,
        period_types=sorted(obs["period_type"].unique()),
        period_start_month=config.period.start_month,
        period_conventions=config.period.convention_summary,
        coverage_start=obs["period_start"].min().date().isoformat(),
        coverage_end=obs["period_end"].max().date().isoformat(),
        indicators=int(obs["indicator_id"].nunique()),
        indicator_units=dict(sorted(units.items())),
        categories=categories,
        has_total_rows=bool(obs["is_total_row"].any()),
        flag_counts={k: int(v) for k, v in sorted(obs["quality_flag"].value_counts().items())},
        caveats=config.dataset.caveats,
    )


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - git is resolved from PATH
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _quality_report(obs: pd.DataFrame) -> pd.DataFrame:
    counts = obs["quality_flag"].value_counts().sort_index()
    rows = [("observations", len(obs)), *[(f"flag_{k}", int(v)) for k, v in counts.items()]]
    return pd.DataFrame(rows, columns=["metric", "value"])


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    frame.to_parquet(path, index=False, engine="pyarrow", compression="snappy")


def _load_previous(config: SourceConfig, directory: Path) -> tuple[pd.DataFrame | None, str]:
    """The live observation table of a dataset, or None with the reason it is not usable."""
    path = directory / f"{config.obs_table}.parquet"
    if not path.exists():
        return None, "none"
    try:
        return pd.read_parquet(path), ""
    except (OSError, ValueError) as error:
        return None, str(error)


def run_with_baseline(
    config: SourceConfig,
    raw_dir: Path,
    profiles_dir: Path | None = None,
    *,
    previous_dir: Path | None = None,
    accept_reason: str | None = None,
) -> RunResult:
    """Run one source, then compare it with its approved profile and with the live release.

    ``accept_reason`` lets a person who has reviewed the blocking changes against the live
    release (re-dated or relabelled periods, revisions, removed rows) release them anyway;
    the reason is kept in the lineage record. Other blocking items are not affected.
    """
    directory = profiles_dir or profile_mod.PROFILES_DIR
    columns, approved_profile = profile_mod.load_approved(config.dataset_id, directory)
    result = run_source(config, raw_dir, approved_columns=columns)
    if approved_profile is not None and not result.obs.empty:
        result.review += profile_mod.compare_profiles(
            config.dataset_id, approved_profile, profile_mod.profile_obs(result.obs)
        )
    if result.obs.empty:
        return result
    previous, reason = _load_previous(config, previous_dir or PROCESSED)
    if previous is None:
        kind, severity = (
            ("no_previous_release", "info")
            if reason == "none"
            else ("previous_release_unreadable", "warn")
        )
        result.review.append(
            ReviewItem(
                dataset_id=config.dataset_id,
                severity=severity,
                kind=kind,
                detail="no live release to compare with" if reason == "none" else reason,
            )
        )
        return result
    items, summary = reconcile.compare_releases(config, previous, result.obs)
    if accept_reason:
        items, accepted = reconcile.accept_changes(items, accept_reason)
        result.lineage["accepted_changes"] = accepted
    result.review += items
    result.lineage["reconciliation"] = summary
    return result


def write_review(result: RunResult, directory: Path = REVIEW_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.config.dataset_id}.csv"
    frame = pd.DataFrame([item.model_dump() for item in result.review])
    if frame.empty:
        frame = pd.DataFrame(
            columns=["dataset_id", "severity", "kind", "detail", "count", "suggestion"]
        )
    order = {"block": 0, "warn": 1, "info": 2}
    frame = frame.sort_values(by="severity", key=lambda s: s.map(order), kind="stable")
    frame.to_csv(path, index=False)
    return path


def publish(
    result: RunResult, out_dir: Path = PROCESSED, lineage_dir: Path = LINEAGE_DIR
) -> dict[str, Any]:
    """Write one dataset's files through a staging folder; returns its catalogue entry."""
    config = result.config
    staging = out_dir / f".staging-{config.dataset_id}"
    staging.mkdir(parents=True, exist_ok=True)
    agent = build_agent_view(config, result.obs)
    files = {
        f"{config.obs_table}.parquet": result.obs,
        f"{config.view.table}.parquet": agent,
    }
    for name, frame in files.items():
        _write_parquet(frame, staging / name)
    _quality_report(result.obs).to_csv(
        staging / f"{config.dataset_id}_quality_report.csv", index=False
    )
    for path in sorted(staging.iterdir()):
        os.replace(path, out_dir / path.name)
    staging.rmdir()

    lineage_dir.mkdir(parents=True, exist_ok=True)
    lineage = {**result.lineage, "git_commit": _git_commit(), "agent_table": config.view.table}
    (lineage_dir / f"{config.dataset_id}.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True, default=str) + "\n"
    )
    entry = build_catalogue_entry(config, result.obs, str(result.lineage["raw_sha256"]))
    return entry.model_dump()


def update_catalogue(entries: list[dict[str, Any]], out_dir: Path = PROCESSED) -> Path:
    """Merge entries into catalogue.json (other datasets keep their last good entry)."""
    path = out_dir / CATALOGUE
    existing: dict[str, Any] = {}
    if path.exists():
        existing = {t["dataset_id"]: t for t in json.loads(path.read_text())["tables"]}
    for entry in entries:
        existing[entry["dataset_id"]] = entry
    document = {
        "contract_version": CONTRACT_VERSION,
        "tables": [existing[key] for key in sorted(existing)],
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path


def write_dim_period(out_dir: Path = PROCESSED) -> Path:
    path = out_dir / "dim_period.parquet"
    _write_parquet(build_dim_period(), path)
    return path


def verify_release(
    configs: list[SourceConfig] | None = None, out_dir: Path = PROCESSED
) -> list[str]:
    """Recompute every catalogue fact from the published files; list any mismatch."""
    problems: list[str] = []
    document = json.loads((out_dir / CATALOGUE).read_text())
    stored = {t["dataset_id"]: t for t in document["tables"]}
    for config in configs or load_all():
        entry = stored.get(config.dataset_id)
        if entry is None:
            problems.append(f"{config.dataset_id}: not in the catalogue")
            continue
        obs = pd.read_parquet(out_dir / f"{config.obs_table}.parquet")
        recomputed = build_catalogue_entry(config, obs, entry["raw_sha256"]).model_dump()
        for key, value in recomputed.items():
            if entry.get(key) != value:
                problems.append(
                    f"{config.dataset_id}: catalogue {key} {entry.get(key)!r} != data {value!r}"
                )
        if not (out_dir / f"{config.view.table}.parquet").exists():
            problems.append(f"{config.dataset_id}: agent table file is missing")
    return problems


def today() -> str:
    return date.today().isoformat()
