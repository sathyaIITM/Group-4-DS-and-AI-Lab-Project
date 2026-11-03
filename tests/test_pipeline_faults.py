"""Fault injection: plant known faults in clean tables and check each one is caught.

For every fault the pipeline must raise a review item of the right kind and must not
change the value on an assumption (the original text stays in ``value_raw``). The
tables are small synthetic frames with the real headers, so the suite runs without the
downloaded raw files.
"""

import hashlib
from pathlib import Path

import pandas as pd
import pytest
from tests.data_fixtures import BUILDERS, approved, config, run

from analyst.data import profile as profile_mod
from analyst.data.engine import RunResult
from analyst.data.publish import _write_parquet


def kinds(result: RunResult, severity: str | None = None) -> set[str]:
    return {i.kind for i in result.review if severity in (None, i.severity)}


def baseline(dataset_id: str) -> tuple[pd.DataFrame, list[str]]:
    frame = BUILDERS[dataset_id]()
    result = run(dataset_id, frame, approved(frame))
    assert not result.blocked, [i for i in result.review if i.severity == "block"]
    return frame, approved(frame)


def test_fault_1_new_missing_marker_blocks_and_keeps_the_text() -> None:
    frame, snapshot = baseline("plfs_state_ur_usual_status")
    frame.loc[0, "_2018_19"] = "NR"
    result = run("plfs_state_ur_usual_status", frame, snapshot)
    assert "unparsed_token" in kinds(result, "block")
    cell = result.obs[
        (result.obs["geo_name"] == "Kerala") & (result.obs["period_label"] == "2018-19")
    ]
    assert cell["value"].isna().all() and cell["value_raw"].iloc[0] == "NR"
    assert cell["quality_flag"].iloc[0] == "unparsed"


def test_fault_2_unit_change_in_a_header_blocks_with_a_rename_hint() -> None:
    frame, snapshot = baseline("nfhs5_district_indicators")
    old = "Out of pocket expenditure per delivery in a public health facility (Rs.)"
    frame = frame.rename(columns={old: old.replace("(Rs.)", "(Rs. lakh)")})
    result = run("nfhs5_district_indicators", frame, snapshot)
    blocking = kinds(result, "block")
    assert {"column_dropped", "column_added"} <= blocking
    hint = next(i.suggestion for i in result.review if i.kind == "column_dropped")
    assert "possible rename" in hint


def test_fault_3_negative_values_are_flagged_and_not_corrected() -> None:
    frame, snapshot = baseline("imd_subdivision_monthly_rainfall")
    frame.loc[0, "jul"] = "-5.0"
    result = run("imd_subdivision_monthly_rainfall", frame, snapshot)
    assert "out_of_range" in kinds(result, "warn")
    hit = result.obs[result.obs["quality_flag"] == "out_of_range"]
    assert len(hit) == 1 and hit["value"].iloc[0] == -5.0 and hit["value_raw"].iloc[0] == "-5.0"


def test_fault_4_renamed_state_blocks_with_a_suggestion() -> None:
    frame, snapshot = baseline("plfs_state_ur_usual_status")
    frame.loc[0, "states_uts"] = "Keralaa"
    result = run("plfs_state_ur_usual_status", frame, snapshot)
    assert "geo_unmatched" in kinds(result, "block")
    item = next(i for i in result.review if i.kind == "geo_unmatched")
    assert "Kerala" in item.suggestion


def test_fault_5_swapped_price_columns_are_flagged_not_reordered() -> None:
    frame, snapshot = baseline("mandi_daily_prices")
    frame[["Min_x0020_Price", "Max_x0020_Price"]] = frame[
        ["Max_x0020_Price", "Min_x0020_Price"]
    ].to_numpy()
    result = run("mandi_daily_prices", frame, snapshot)
    assert "inconsistent" in kinds(result, "warn")
    flagged = result.obs[result.obs["quality_flag"] == "inconsistent"]
    assert set(flagged["checks_failed"]) == {"price_order"}
    assert (
        flagged[flagged["indicator_id"] == "min_price_inr_per_quintal"]["value"].iloc[0] == 2400.0
    )


def test_fault_6_duplicated_rows_block() -> None:
    frame, snapshot = baseline("imd_subdivision_monthly_rainfall")
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    result = run("imd_subdivision_monthly_rainfall", frame, snapshot)
    assert "duplicate_key" in kinds(result, "block")
    item = next(i for i in result.review if i.kind == "duplicate_key")
    assert item.count == 2 * 17  # the repeated row holds 17 values, present twice


def test_fault_7_dropped_column_blocks() -> None:
    frame, snapshot = baseline("imd_subdivision_monthly_rainfall")
    result = run("imd_subdivision_monthly_rainfall", frame.drop(columns="jjas"), snapshot)
    assert "column_missing" in kinds(result, "block")
    assert result.obs.empty  # nothing is published from a table that lost a column


def test_fault_8_new_date_format_blocks() -> None:
    frame, snapshot = baseline("mandi_daily_prices")
    frame.loc[0, "Arrival_Date"] = "2026-10-29"
    result = run("mandi_daily_prices", frame, snapshot)
    assert "unparsed_period" in kinds(result, "block")
    bad = result.obs[result.obs["source_row"] == 0]
    assert set(bad["quality_flag"]) == {"unparsed"} and bad["period_start"].isna().all()


# --- Change drills: the situations raised in the TA review --------------------------------


def test_year_convention_must_be_stated() -> None:
    cfg = config("plfs_state_ur_usual_status")
    cfg.period.start_month = None
    from analyst.data.engine import run_source

    result = run_source(cfg, Path("data/raw"), raw_frame=BUILDERS["plfs_state_ur_usual_status"]())
    assert "period_convention_unknown" in kinds(result, "block")
    assert result.obs.empty


def test_changing_the_year_start_month_moves_every_period_boundary() -> None:
    frame = BUILDERS["plfs_state_ur_usual_status"]()
    july = run("plfs_state_ur_usual_status", frame, approved(frame)).obs
    cfg = config("plfs_state_ur_usual_status")
    cfg.period.start_month = 4
    from analyst.data.engine import run_source

    april = run_source(cfg, Path("data/raw"), raw_frame=frame, approved_columns=approved(frame)).obs

    def row(obs: pd.DataFrame) -> pd.Series:
        match = (obs["geo_name"] == "Kerala") & (obs["period_label"] == "2017-18")
        return obs[match].iloc[0]

    assert (str(row(july)["period_start"].date()), str(row(july)["period_end"].date())) == (
        "2017-07-01",
        "2018-06-30",
    )
    assert (str(row(april)["period_start"].date()), str(row(april)["period_end"].date())) == (
        "2017-04-01",
        "2018-03-31",
    )


def test_a_new_period_column_is_accepted_and_reported_as_info() -> None:
    frame, snapshot = baseline("plfs_state_ur_usual_status")
    frame["_2019_20"] = ["8.0", "7.0", "6.0", "5.0"]
    result = run("plfs_state_ur_usual_status", frame, snapshot)
    assert not result.blocked and "new_period" in kinds(result, "info")
    assert "2019-20" in set(result.obs["period_label"])


def test_a_new_period_format_blocks() -> None:
    frame, snapshot = baseline("plfs_state_ur_usual_status")
    frame = frame.rename(columns={"_2018_19": "FY2018-19"})
    assert "column_added" in kinds(run("plfs_state_ur_usual_status", frame, snapshot), "block")


def test_exact_duplicate_mandi_rows_are_removed_and_reported() -> None:
    frame, snapshot = baseline("mandi_daily_prices")
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    result = run("mandi_daily_prices", frame, snapshot)
    assert not result.blocked and "duplicates_removed" in kinds(result, "info")
    assert result.lineage["rows_in"] - result.lineage["rows_after_dedupe"] == 1


def test_unmatched_place_in_a_known_alias_resolves_without_blocking() -> None:
    frame, snapshot = baseline("mandi_daily_prices")  # contains Keralam
    result = run("mandi_daily_prices", frame, snapshot)
    kerala = result.obs[result.obs["geo_state_source"] == "Keralam"]
    assert set(kerala["geo_state"]) == {"Kerala"} and set(kerala["geo_match"]) == {"alias"}


def test_missing_snapshot_is_a_warning_not_a_silent_pass() -> None:
    frame = BUILDERS["plfs_state_ur_usual_status"]()
    result = run("plfs_state_ur_usual_status", frame, None)
    assert "no_column_snapshot" in kinds(result, "warn")


# --- Distribution drift between refreshes ----------------------------------------------------


def test_unit_scale_jump_between_refreshes_blocks() -> None:
    frame, snapshot = baseline("mandi_daily_prices")
    approved_profile = profile_mod.profile_obs(run("mandi_daily_prices", frame, snapshot).obs)
    scaled = frame.copy()
    for column in ("Min_x0020_Price", "Max_x0020_Price", "Modal_x0020_Price"):
        scaled[column] = (scaled[column].astype(float) * 100).astype(int).astype(str)
    now = profile_mod.profile_obs(run("mandi_daily_prices", scaled, snapshot).obs)
    items = profile_mod.compare_profiles("mandi_daily_prices", approved_profile, now)
    assert {i.kind for i in items if i.severity == "block"} == {"unit_change_suspected"}


def test_small_shift_warns_and_large_row_change_warns() -> None:
    approved_profile = {
        "observations": 100,
        "indicators": {"x": {"median": 10.0, "mad": 1.0, "p05": 8, "p95": 12}},
    }
    current = {
        "observations": 150,
        "indicators": {"x": {"median": 20.0, "mad": 1.0, "p05": 18, "p95": 22}},
    }
    items = profile_mod.compare_profiles("d", approved_profile, current)
    assert {i.kind for i in items} == {"distribution_shift", "volume_change"}
    assert all(i.severity == "warn" for i in items)


# --- Reproducibility ---------------------------------------------------------------------------


@pytest.mark.parametrize("dataset_id", sorted(BUILDERS))
def test_two_runs_give_byte_identical_files(dataset_id: str, tmp_path: Path) -> None:
    frame = BUILDERS[dataset_id]()
    digests = []
    for attempt in ("a", "b"):
        obs = run(dataset_id, frame.copy(), approved(frame)).obs
        path = tmp_path / f"{attempt}.parquet"
        _write_parquet(obs, path)
        digests.append(hashlib.sha256(path.read_bytes()).hexdigest())
    assert digests[0] == digests[1]
