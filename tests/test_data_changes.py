"""Changes in public data that the pipeline must survive or make visible.

Year windows that move, quarters, places spelt differently, tables that are republished
with other labels or revised values, and checks that name something that is not there.
"""

import tomllib
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError
from tests.data_fixtures import (
    BUILDERS,
    approved,
    config,
    config_from_toml,
    edited,
    run,
    run_config,
)

from analyst.data import ops, reconcile
from analyst.data.config import SourceConfig
from analyst.data.contract import PERIOD_TYPES
from analyst.data.engine import RunResult
from analyst.data.publish import _write_parquet, build_catalogue_entry, run_with_baseline

PLFS = "plfs_state_ur_usual_status"
IMD = "imd_subdivision_monthly_rainfall"
MANDI = "mandi_daily_prices"


def kinds(items: object, severity: str | None = None) -> set[str]:
    review = items.review if isinstance(items, RunResult) else items
    return {i.kind for i in review if severity in (None, i.severity)}  # type: ignore[attr-defined]


def plfs_frame(*years: str) -> pd.DataFrame:
    frame = BUILDERS[PLFS]()[["sl__no_", "states_uts"]].copy()
    for year in years:
        frame[year] = ["9.0", "7.0", "8.0", "5.0"]
    return frame


def plfs_obs(cfg: SourceConfig | None = None, *years: str) -> pd.DataFrame:
    frame = plfs_frame(*(years or ("_2017_18", "_2018_19")))
    result = run_config(cfg or config(PLFS), frame, approved(frame))
    assert not result.blocked, [i for i in result.review if i.severity == "block"]
    return result.obs


# --- Place names --------------------------------------------------------------------------


def test_names_differing_only_in_case_or_spacing_match_as_alias() -> None:
    canonical = {"Jammu and Kashmir", "Kerala"}
    names, status = ops.match_names(
        pd.Series(["Jammu And Kashmir", "KERALA", "Kerala ", "Atlantis"]), canonical, {}, set()
    )
    assert list(names) == ["Jammu and Kashmir", "Kerala", "Kerala", "Atlantis"]
    assert list(status) == ["alias", "alias", "alias", "unmatched"]


def test_two_canonical_names_with_one_normal_form_are_never_guessed() -> None:
    _, status = ops.match_names(pd.Series(["A b"]), {"A B", "a b"}, {}, set())
    assert list(status) == ["unmatched"]


def test_state_names_in_title_case_resolve_on_a_real_table() -> None:
    frame = plfs_frame("_2017_18")
    frame.loc[0, "states_uts"] = "KERALA"
    result = run_config(config(PLFS), frame, approved(frame))
    row = result.obs[result.obs["geo_name_source"] == "KERALA"]
    assert set(row["geo_name"]) == {"Kerala"} and set(row["geo_match"]) == {"alias"}
    assert "geo_unmatched" not in kinds(result)


def reference_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, alias_rows: str = "") -> None:
    directory = tmp_path / "reference"
    directory.mkdir()
    for source in Path("configs/reference").glob("*.csv"):
        (directory / source.name).write_text(source.read_text())
    if alias_rows:
        with (directory / "subdivision_aliases.csv").open("a") as handle:
            handle.write(alias_rows)
    monkeypatch.setattr(ops, "REFERENCE_DIR", directory)


def imd_with_subdivision(name: str) -> pd.DataFrame:
    frame = BUILDERS[IMD]()
    frame.loc[0, "subdivision"] = name
    return frame


def test_subdivision_spellings_resolve_through_the_alias_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference_copy(tmp_path, monkeypatch, "LAKSHDWEEP,Lakshadweep,test spelling\n")
    names = pd.read_csv(tmp_path / "reference" / "imd_subdivisions.csv")["subdivision"]
    assert "Lakshadweep" in set(names)
    frame = imd_with_subdivision("LAKSHDWEEP")
    result = run(IMD, frame, approved(frame))
    row = result.obs[result.obs["geo_name_source"] == "LAKSHDWEEP"]
    assert set(row["geo_name"]) == {"Lakshadweep"} and set(row["geo_match"]) == {"alias"}
    assert set(row["geo_code"]) == {"subdivision:lakshadweep"}
    assert "geo_unmatched" not in kinds(result)


def test_an_unlisted_subdivision_blocks_and_points_at_the_subdivision_alias_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference_copy(tmp_path, monkeypatch)
    frame = imd_with_subdivision("LAKSHDWEEP")
    result = run(IMD, frame, approved(frame))
    item = next(i for i in result.review if i.kind == "geo_unmatched")
    assert item.severity == "block" and "subdivision_aliases.csv" in item.suggestion
    assert "Lakshadweep" in item.suggestion


# --- Periods ---------------------------------------------------------------------------------


def test_a_header_with_one_year_gets_a_label_from_the_declared_window() -> None:
    frame = plfs_frame("_2017")
    july = edited(PLFS, values={"pattern": r"^_(\d{4})$"})
    obs = run_config(july, frame, approved(frame)).obs
    assert set(obs["period_label"]) == {"2017-18"}
    january = edited(PLFS, values={"pattern": r"^_(\d{4})$"}, period={"start_month": 1})
    obs = run_config(january, frame, approved(frame)).obs
    assert set(obs["period_label"]) == {"2017"}
    assert str(obs["period_end"].iloc[0].date()) == "2017-12-31"


def test_quarter_period_type_is_part_of_the_contract() -> None:
    assert "quarter" in PERIOD_TYPES


QUARTERS_BASE = """
[dataset]
id = "t_quarterly"
domain = "labour"
title = "t"
source_name = "s"
source_table = "s"
publisher = "p"
raw_file = "x.csv"
config_version = "0.1.0"
retrieved = "2026-11-03"

[columns]
year = "period_year"
quarter = "period_quarter"
state_name = "geo_state"
gender = "category:gender"

[values]
mode = "indicators"

[values.columns.value]
id = "lfpr"
unit = "percent"

[period]
type = "quarter"

[geo]
level = "state"
vintage = "t"
state_reference = "states"
total_members = ["All-India"]

[view]
mode = "rows"
table = "t_quarterly"

[view.columns]
state_name = "geo_name"
"""

QUARTER_MAP = """
[period.quarter_map."January-March"]
label = "Q1"
start_month = 1
end_month = 3

[period.quarter_map."April-June"]
label = "Q2"
start_month = 4
end_month = 6

[period.quarter_map."October-December"]
label = "Q4"
start_month = 10
end_month = 12
"""
QUARTERS = QUARTERS_BASE + QUARTER_MAP


def quarter_frame(years: list[str], quarters: list[str]) -> pd.DataFrame:
    n = len(years)
    return pd.DataFrame(
        {
            "year": years,
            "quarter": quarters,
            "state_name": ["Kerala"] * n,
            "gender": ["Male"] * n,
            "value": [str(50 + i) for i in range(n)],
        }
    )


def test_quarters_get_their_own_dates_and_labels() -> None:
    cfg = config_from_toml(QUARTERS)
    frame = quarter_frame(
        ["2019", "2019", "2019"], ["April-June", "January-March", "October-December"]
    )
    result = run_config(cfg, frame, approved(frame))
    assert not result.blocked, result.review
    spans = {
        r.period_label: (str(r.period_start.date()), str(r.period_end.date()))
        for r in result.obs.itertuples()
    }
    assert spans == {
        "2019-Q2": ("2019-04-01", "2019-06-30"),
        "2019-Q1": ("2019-01-01", "2019-03-31"),
        "2019-Q4": ("2019-10-01", "2019-12-31"),
    }
    assert set(result.obs["period_type"]) == {"quarter"}


def test_a_fiscal_quarter_after_december_moves_into_the_next_calendar_year() -> None:
    text = QUARTERS.replace(
        'label = "Q1"\nstart_month = 1\nend_month = 3',
        'label = "Q4"\nstart_month = 1\nend_month = 3\nyear_offset = 1',
    )
    cfg = config_from_toml(text)
    frame = quarter_frame(["2023"], ["January-March"])
    obs = run_config(cfg, frame, approved(frame)).obs
    assert obs["period_label"].iloc[0] == "2023-Q4"
    assert str(obs["period_start"].iloc[0].date()) == "2024-01-01"


def test_an_unknown_quarter_name_blocks_and_flags_the_value() -> None:
    cfg = config_from_toml(QUARTERS)
    frame = quarter_frame(["2019", "2019"], ["April-June", "Monsoon"])
    result = run_config(cfg, frame, approved(frame))
    assert "unparsed_period" in kinds(result, "block")
    bad = result.obs[result.obs["period_source"] == "2019 Monsoon"]
    assert set(bad["quality_flag"]) == {"unparsed"} and bad["period_start"].isna().all()


def test_a_quarter_table_without_a_quarter_map_is_refused() -> None:
    with pytest.raises(ValidationError):
        config_from_toml(QUARTERS_BASE)


# --- A year window that moves --------------------------------------------------------------


def window(obs: pd.DataFrame, label: str) -> tuple[str, str]:
    row = obs[obs["period_label"] == label].iloc[0]
    return str(row["period_start"].date()), str(row["period_end"].date())


def test_a_later_convention_leaves_earlier_years_on_their_old_window() -> None:
    cfg = edited(
        PLFS,
        period={
            "conventions": [{"from_year": 2019, "start_month": 4}],
            "exceptions": [{"year": 2018, "start": "2018-07-01", "end": "2019-03-31"}],
        },
    )
    obs = plfs_obs(cfg, "_2017_18", "_2018_19", "_2019_20")
    assert window(obs, "2017-18") == ("2017-07-01", "2018-06-30")
    assert window(obs, "2018-19") == ("2018-07-01", "2019-03-31")  # the stated transition year
    assert window(obs, "2019-20") == ("2019-04-01", "2020-03-31")


def test_mixed_windows_without_a_transition_year_overlap_and_block() -> None:
    cfg = edited(PLFS, period={"conventions": [{"from_year": 2019, "start_month": 4}]})
    frame = plfs_frame("_2017_18", "_2018_19", "_2019_20")
    result = run_config(cfg, frame, approved(frame))
    assert "period_overlap" in kinds(result, "block")
    item = next(i for i in result.review if i.kind == "period_overlap")
    assert "2018-19 -> 2019-20" in item.detail and "period.exceptions" in item.suggestion


def test_periods_that_follow_each_other_raise_nothing() -> None:
    frame = plfs_frame("_2017_18", "_2018_19", "_2019_20")
    result = run(PLFS, frame, approved(frame))
    assert kinds(result) & {"period_overlap", "period_gap"} == set()


def test_a_missing_year_is_reported_as_a_gap_not_dropped_silently() -> None:
    frame = plfs_frame("_2017_18", "_2019_20")
    result = run(PLFS, frame, approved(frame))
    assert "period_gap" in kinds(result, "warn") and not result.blocked
    quiet = edited(PLFS, period={"expect_contiguous": False})
    assert "period_gap" not in kinds(run_config(quiet, frame, approved(frame)))


def test_periods_after_the_last_confirmed_year_are_published_with_a_warning() -> None:
    frame = plfs_frame("_2017_18", "_2018_19", "_2019_20")
    cfg = edited(PLFS, period={"verified_through": 2018})
    item = next(
        i
        for i in run_config(cfg, frame, approved(frame)).review
        if i.kind == "year_window_unverified"
    )
    assert item.severity == "warn" and "2019-20" in item.detail and "2018-19" not in item.detail
    confirmed = edited(PLFS, period={"verified_through": 2019})
    assert "year_window_unverified" not in kinds(run_config(confirmed, frame, approved(frame)))


@pytest.mark.parametrize(
    "period",
    [
        {
            "conventions": [
                {"from_year": 2020, "start_month": 4},
                {"from_year": 2019, "start_month": 1},
            ]
        },
        {"exceptions": [{"year": 2018, "start": "2019-03-31", "end": "2018-07-01"}]},
    ],
)
def test_inconsistent_window_declarations_are_refused(period: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        edited(PLFS, period=period)


def test_the_catalogue_states_the_window_changes() -> None:
    cfg = edited(
        PLFS,
        period={
            "conventions": [{"from_year": 2019, "start_month": 4}],
            "exceptions": [{"year": 2018, "start": "2018-07-01", "end": "2019-03-31"}],
        },
    )
    obs = plfs_obs(cfg, "_2017_18", "_2018_19", "_2019_20")
    entry = build_catalogue_entry(cfg, obs, "abc")
    assert entry.period_conventions == [{"from_year": 2019, "start_month": 4}]


# --- Checks that cannot run -------------------------------------------------------------------


def test_a_check_naming_an_unknown_indicator_is_reported_not_skipped() -> None:
    cfg = config(PLFS)
    cfg.checks[0].indicators = ["not_an_indicator"]
    frame = plfs_frame("_2017_18")
    result = run_config(cfg, frame, approved(frame))
    item = next(i for i in result.review if i.kind == "check_target_missing")
    assert item.severity == "warn" and "not_an_indicator" in item.detail


# --- Release against release ------------------------------------------------------------------


def test_an_identical_release_changes_nothing() -> None:
    obs = plfs_obs()
    items, summary = reconcile.compare_releases(config(PLFS), obs, obs.copy())
    assert [i for i in items if i.severity != "info"] == []
    assert summary["revised"] == 0 and summary["removed"] == 0 and summary["redated"] == 0


def test_moving_the_window_of_years_already_published_blocks() -> None:
    old = plfs_obs()
    shifted = edited(PLFS, period={"start_month": 4})
    new = plfs_obs(shifted)
    items, summary = reconcile.compare_releases(shifted, old, new)
    assert "period_redated" in kinds(items, "block")
    assert summary["redated"] == len(old)


def test_a_new_year_appended_is_information_only() -> None:
    old = plfs_obs(None, "_2017_18", "_2018_19")
    new = plfs_obs(None, "_2017_18", "_2018_19", "_2019_20")
    items, summary = reconcile.compare_releases(config(PLFS), old, new)
    assert kinds(items) == {"rows_added"} and summary["added"] == 4


def test_a_few_revised_values_warn_and_a_wholesale_revision_blocks() -> None:
    frame = BUILDERS[IMD]()
    old = run(IMD, frame, approved(frame)).obs
    few = old.copy()
    few.loc[few.index[3], "value"] += 5.0
    items, _ = reconcile.compare_releases(config(IMD), old, few)
    assert "values_revised" in kinds(items, "warn") and not kinds(items, "block")
    many = old.copy()
    many["value"] = many["value"] * 1.5
    items, _ = reconcile.compare_releases(config(IMD), old, many)
    assert "values_revised" in kinds(items, "block")


def test_dropping_old_years_warns_and_a_large_cut_blocks() -> None:
    old = plfs_obs(None, "_2017_18", "_2018_19")
    items, summary = reconcile.compare_releases(
        config(PLFS), old, old[old["period_label"] != "2017-18"]
    )
    assert "rows_removed" in kinds(items, "block")  # half of the history is a large cut
    assert summary["removed"] == 4
    big = plfs_obs(None, "_2017_18", "_2018_19")
    cfg = edited(PLFS, reconcile={"max_removed_share": 0.9})
    items, _ = reconcile.compare_releases(cfg, big, big[big["period_label"] != "2017-18"])
    assert "rows_removed" in kinds(items, "warn")


def test_a_renamed_period_with_the_same_dates_is_a_relabel_not_a_removal() -> None:
    old = plfs_obs()
    new = old.copy()
    new["period_label"] = new["period_label"].str.replace("-", "/", regex=False)
    items, summary = reconcile.compare_releases(config(PLFS), old, new)
    assert "period_relabelled" in kinds(items, "block")
    assert "rows_removed" not in kinds(items) and summary["relabelled"] == len(old)


def test_a_lost_indicator_a_changed_unit_and_a_lost_column_block() -> None:
    frame = BUILDERS[MANDI]()
    old = run(MANDI, frame, approved(frame)).obs
    fewer = old[old["indicator_id"] != "min_price_inr_per_quintal"]
    assert "indicators_removed" in kinds(
        reconcile.compare_releases(config(MANDI), old, fewer)[0], "block"
    )
    other_unit = old.copy()
    other_unit.loc[other_unit["indicator_id"] == "modal_price_inr_per_quintal", "unit"] = (
        "INR_per_kg"
    )
    assert "unit_changed" in kinds(
        reconcile.compare_releases(config(MANDI), old, other_unit)[0], "block"
    )
    narrower = old.drop(columns=["variety"])
    assert "category_columns_changed" in kinds(
        reconcile.compare_releases(config(MANDI), old, narrower)[0], "block"
    )


def test_new_places_and_new_category_values_are_reported_as_information() -> None:
    frame = BUILDERS[MANDI]()
    old = run(MANDI, frame, approved(frame)).obs
    extra = old.iloc[[0]].copy()
    extra["geo_code"] = "market:odisha/puri/puri"
    extra["commodity_name"] = "Garlic"
    items, _ = reconcile.compare_releases(config(MANDI), old, pd.concat([old, extra]))
    assert {"places_added", "category_values_added"} <= kinds(items, "info")
    assert not kinds(items, "block")


def test_accepting_changes_records_the_reason_and_leaves_other_blocks_alone() -> None:
    old = plfs_obs()
    shifted = edited(PLFS, period={"start_month": 4})
    items, _ = reconcile.compare_releases(shifted, old, plfs_obs(shifted))
    unrelated = reconcile.ReviewItem(
        dataset_id="d", severity="block", kind="duplicate_key", detail="x"
    )
    kept, accepted = reconcile.accept_changes([*items, unrelated], "publisher moved to April-March")
    assert kinds(kept, "block") == {"duplicate_key"}
    assert accepted == [
        {"kind": "period_redated", "count": len(old), "reason": "publisher moved to April-March"}
    ]
    assert (
        "accepted (publisher moved to April-March)"
        in next(i for i in kept if i.kind == "period_redated").detail
    )


def write_raw(cfg: SourceConfig, frame: pd.DataFrame, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / cfg.dataset.raw_file, index=False)
    return directory


def test_a_republished_table_is_compared_with_the_live_one(tmp_path: Path) -> None:
    frame = plfs_frame("_2017_18", "_2018_19")
    live = tmp_path / "live"
    live.mkdir()
    cfg = config(PLFS)
    raw = write_raw(cfg, frame, tmp_path / "raw")
    first = run_with_baseline(cfg, raw, tmp_path / "profiles", previous_dir=live)
    assert "no_previous_release" in kinds(first, "info") and not first.blocked
    _write_parquet(first.obs, live / f"{cfg.obs_table}.parquet")

    unchanged = run_with_baseline(cfg, raw, tmp_path / "profiles", previous_dir=live)
    assert not unchanged.blocked and unchanged.lineage["reconciliation"]["revised"] == 0

    shifted = edited(PLFS, period={"start_month": 4})
    blocked = run_with_baseline(shifted, raw, tmp_path / "profiles", previous_dir=live)
    assert blocked.blocked and "period_redated" in kinds(blocked, "block")

    accepted = run_with_baseline(
        shifted, raw, tmp_path / "profiles", previous_dir=live, accept_reason="source corrected"
    )
    assert not accepted.blocked
    assert accepted.lineage["accepted_changes"][0]["reason"] == "source corrected"


def test_the_command_refuses_to_accept_changes_for_every_table_at_once() -> None:
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "scripts/run_pipeline.py", "--accept-changes", "because"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1 and "--dataset" in done.stdout


def test_toml_configs_for_the_five_tables_still_load() -> None:
    for path in Path("configs/sources").glob("*.toml"):
        assert tomllib.loads(path.read_text())["dataset"]["id"] == path.stem


# --- Seasonal subsets and daily series ---------------------------------------------------------

SEASONAL = """
[dataset]
id = "t_monsoon"
domain = "rainfall"
title = "t"
source_name = "s"
source_table = "s"
publisher = "p"
raw_file = "x.csv"
config_version = "0.1.0"
retrieved = "2026-11-03"

[columns]
subdivision = "geo_subdivision"
YEAR = "period_year"

[values]
mode = "periods"

[values.indicator]
id = "rainfall_mm"
unit = "mm"

[values.period_columns]
JUN = { type = "month", start_month = 6, end_month = 6 }
SEP = { type = "month", start_month = 9, end_month = 9 }
"JUN-SEP" = { type = "season", start_month = 6, end_month = 9 }

[period]
type = "calendar_year"

[geo]
level = "subdivision"
vintage = "t"
subdivision_reference = "imd_subdivisions"

[view]
mode = "pivot_period"
table = "t_monsoon"
columns = { subdivision = "geo_name_source" }
"""


def monsoon_frame(years: list[int]) -> pd.DataFrame:
    rows = [
        [name, str(year), "100", "200", "300"] for name in ("Kerala", "Orissa") for year in years
    ]
    return pd.DataFrame(rows, columns=["subdivision", "YEAR", "JUN", "SEP", "JUN-SEP"])


def test_a_table_holding_only_the_monsoon_months_is_not_a_gap() -> None:
    frame = monsoon_frame([1950, 1951, 1952])
    result = run_config(config_from_toml(SEASONAL), frame, approved(frame))
    assert "period_gap" not in kinds(result) and not result.blocked


def test_a_missing_year_is_one_gap_per_series_however_many_periods_it_had() -> None:
    frame = monsoon_frame([1950, 1951, 1953])
    result = run_config(config_from_toml(SEASONAL), frame, approved(frame))
    item = next(i for i in result.review if i.kind == "period_gap")
    assert item.count == 2  # Kerala and Orissa, each missing 1952, in June, September and season
    assert "1951-06 -> 1953-06" in item.detail


DAILY = """
[dataset]
id = "t_daily"
domain = "rainfall"
title = "t"
source_name = "s"
source_table = "s"
publisher = "p"
raw_file = "x.csv"
config_version = "0.1.0"
retrieved = "2026-11-03"

[columns]
date = "period_date"
state = "geo_state"

[values]
mode = "indicators"

[values.columns.rain]
id = "rain_mm"
unit = "mm"

[period]
type = "date"
date_format = "%Y-%m-%d"
EXPECT

[geo]
level = "state"
vintage = "t"
state_reference = "states"

[view]
mode = "rows"
table = "t_daily"

[view.columns]
state = "geo_name"
"""


def test_missing_days_are_reported_only_when_the_source_is_meant_to_be_daily() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-05"],
            "state": ["Kerala"] * 3,
            "rain": ["1.0", "2.0", "3.0"],
        }
    )
    silent = run_config(config_from_toml(DAILY.replace("EXPECT", "")), frame, approved(frame))
    assert "period_gap" not in kinds(silent)
    strict = DAILY.replace("EXPECT", "expect_contiguous = true")
    result = run_config(config_from_toml(strict), frame, approved(frame))
    assert "period_gap" in kinds(result, "warn")


def test_a_total_row_is_recognised_whatever_its_case() -> None:
    frame = plfs_frame("_2017_18")
    frame.loc[3, "states_uts"] = "ALL INDIA"
    result = run_config(config(PLFS), frame, approved(frame))
    total = result.obs[result.obs["geo_name_source"] == "ALL INDIA"]
    assert total["is_total_row"].all() and set(total["geo_level"]) == {"national"}
    assert set(total["geo_name"]) == {"India"} and "geo_unmatched" not in kinds(result)
