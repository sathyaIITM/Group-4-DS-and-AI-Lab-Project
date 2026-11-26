"""Tests for the place reference files of Milestone 5 (State to IMD sub-division map, aliases)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from analyst.tools.places import alias_lookup, map_state_to_subdivisions

REFERENCE = Path("configs/reference")
SUBDIVISIONS = REFERENCE / "imd_subdivisions.csv"
IMD_TABLE = Path("data/processed/obs_imd_subdivision_monthly_rainfall.parquet")


def subdivisions() -> pd.DataFrame:
    """Return the sub-division reference with its State lists."""
    return pd.read_csv(SUBDIVISIONS, dtype=str)


def states(status: str | None = None) -> set[str]:
    """Return the State and UT names of ``states.csv``, optionally of one status."""
    frame = pd.read_csv(REFERENCE / "states.csv", dtype=str)
    if status is not None:
        frame = frame[frame["status"] == status]
    return set(frame["state_name"])


def test_every_subdivision_lists_known_states_and_a_source() -> None:
    """Each row names at least one State spelled as in ``states.csv``, and its source."""
    frame = subdivisions()
    assert list(frame.columns[:1]) == ["subdivision"]  # the pipeline reads the first column
    assert frame["states"].notna().all() and frame["source"].notna().all()
    named = {part for value in frame["states"] for part in value.split(";")}
    assert named <= states(), sorted(named - states())


def test_every_current_state_maps_to_a_subdivision() -> None:
    """No current State or UT is left without a sub-division."""
    named = {part for value in subdivisions()["states"] for part in value.split(";")}
    assert states("current") <= named, sorted(states("current") - named)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            "Karnataka",
            ["Coastal Karnataka", "North Interior Karnataka", "South Interior Karnataka"],
        ),
        ("Delhi", ["Haryana Delhi & Chandigarh"]),
        ("Odisha", ["Orissa"]),
        ("Goa", ["Konkan & Goa"]),
    ],
)
def test_split_shared_and_renamed_states_map_to_their_subdivisions(
    state: str, expected: list[str]
) -> None:
    """A split State lists each sub-division; a shared or renamed one finds its own."""
    assert map_state_to_subdivisions(state, {"imd_subdivisions": SUBDIVISIONS}) == expected


def test_subdivision_aliases_point_at_listed_subdivisions() -> None:
    """Every sub-division alias resolves to a name of ``imd_subdivisions.csv``."""
    aliases = pd.read_csv(REFERENCE / "subdivision_aliases.csv", dtype=str)
    assert set(aliases["canonical"]) <= set(subdivisions()["subdivision"])
    refs = {"subdivision_aliases": REFERENCE / "subdivision_aliases.csv"}
    assert alias_lookup("Marathwada", refs) == "Matathwada"


DISTRICT_TABLES = (
    "nfhs5_district_indicators",
    "crop_production_district",
    "imd_district_rainfall_normals",
)


def test_duplicate_districts_list_each_name_in_at_least_two_states() -> None:
    """Every listed district name occurs with two or more States in the same table."""
    frame = pd.read_csv(REFERENCE / "duplicate_districts.csv", dtype=str)
    assert set(frame["dataset_id"]) <= set(DISTRICT_TABLES)
    assert frame.groupby(["dataset_id", "district"])["state"].nunique().min() >= 2
    assert frame["state"].isin(states()).all()


@pytest.mark.parametrize("dataset_id", DISTRICT_TABLES)
def test_duplicate_districts_match_the_published_table(dataset_id: str) -> None:
    """The file lists exactly the district names shared by States in each table."""
    path = Path(f"data/processed/obs_{dataset_id}.parquet")
    if not path.exists():
        pytest.skip("needs the published district tables")
    table = pd.read_parquet(path, columns=["geo_level", "geo_name", "geo_state"])
    table = table[table["geo_level"] == "district"].drop_duplicates()
    shared = table.groupby("geo_name")["geo_state"].nunique()
    expected = set(
        table[table["geo_name"].isin(shared[shared > 1].index)][
            ["geo_name", "geo_state"]
        ].itertuples(index=False, name=None)
    )
    frame = pd.read_csv(REFERENCE / "duplicate_districts.csv", dtype=str)
    listed = frame[frame["dataset_id"] == dataset_id]
    assert set(zip(listed["district"], listed["state"], strict=True)) == expected


@pytest.mark.skipif(not IMD_TABLE.exists(), reason="needs the published IMD table")
def test_subdivision_names_match_the_published_table() -> None:
    """The reference lists exactly the sub-divisions stored in the IMD table."""
    stored = set(pd.read_parquet(IMD_TABLE, columns=["geo_name"])["geo_name"])
    assert set(subdivisions()["subdivision"]) == stored
