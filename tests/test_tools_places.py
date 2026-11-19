"""Tests for place resolution."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from analyst.tools.places import (
    PlaceResolution,
    alias_lookup,
    map_state_to_subdivisions,
    normalise,
    places_in_table,
    resolve_place,
)


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute(
        """CREATE TABLE obs_demo (
            dataset_version VARCHAR, geo_code VARCHAR, geo_name VARCHAR,
            geo_level VARCHAR, geo_vintage VARCHAR
        )"""
    )
    connection.executemany(
        "INSERT INTO obs_demo VALUES (?, ?, ?, ?, ?)",
        [
            ("v1", "state:odisha", "Odisha", "state", "current"),
            ("v1", "state:assam", "Assam", "state", "current"),
            ("v1", "district:khordha", "Khordha", "district", "2011"),
        ],
    )
    return connection


def test_normalise_handles_ampersands_punctuation_and_spacing() -> None:
    assert normalise("  Jammu & Kashmir!! ") == "jammu and kashmir"


def test_alias_lookup_accepts_reference_dataframe() -> None:
    refs = {"place_aliases": pd.DataFrame([{"alias": "Orissa", "canonical": "Odisha"}])}
    assert alias_lookup("orissa", refs) == "Odisha"


def test_places_in_table_returns_sorted_names(db: duckdb.DuckDBPyConnection) -> None:
    assert places_in_table("demo", "state", db) == ["Assam", "Odisha"]


def test_resolve_place_exact_and_alias(db: duckdb.DuckDBPyConnection) -> None:
    exact = resolve_place("Odisha", "demo", "state", {}, db)
    assert exact.status == "exact"
    assert exact.place is not None
    assert exact.place.model_dump() == {
        "requested": "Odisha",
        "level": "state",
        "code": "state:odisha",
        "name": "Odisha",
        "match": "exact",
        "vintage": "current",
    }
    refs = {"place_aliases": {"Orissa": "Odisha"}}
    result = resolve_place("Orissa", "demo", "state", refs, db)
    assert result.status == "alias"
    assert result.place is not None and result.place.name == "Odisha"


def test_resolve_place_case_spacing_alias_and_unresolved(db: duckdb.DuckDBPyConnection) -> None:
    result = resolve_place("  odisha ", "demo", "state", {}, db)
    assert result.status == "alias"
    unresolved = resolve_place("Odi", "demo", "state", {}, db)
    assert unresolved == PlaceResolution(status="unresolved", options=["Odisha"])
    assert resolve_place("Odissha", "demo", "state", {}, db).options == []


def test_rejects_unsafe_dataset_id(db: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ValueError, match="dataset_id"):
        places_in_table("demo; DROP TABLE obs_demo", "state", db)


def test_state_subdivision_mapping_requires_explicit_relationship() -> None:
    refs = {
        "imd_subdivisions": pd.DataFrame(
            [{"state": "Andhra Pradesh", "subdivision": "Coastal Andhra Pradesh"}]
        )
    }
    assert map_state_to_subdivisions("Andhra Pradesh", refs) == ["Coastal Andhra Pradesh"]
    with pytest.raises(ValueError, match="state mappings"):
        map_state_to_subdivisions(
            "Andhra Pradesh", {"imd_subdivisions": pd.DataFrame([{"subdivision": "x"}])}
        )
