"""Milestone 5 place fixes (A1-A4): State to IMD sub-division, aliases, same-named districts."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analyst.contracts import QueryIntent
from analyst.tools.places import alias_candidates, resolve_place, split_qualifier
from analyst.tools.resolve import resolve_plan
from analyst.tools.sql_runner import ReadOnlyDatabase

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "configs" / "reference"
PROCESSED = ROOT / "data" / "processed"
needs_data = pytest.mark.skipif(
    not list(PROCESSED.glob("obs_*.parquet")), reason="published tables are not present"
)

SUBDIVISIONS = pd.DataFrame(
    {
        "subdivision": [
            "Coastal Karnataka",
            "North Interior Karnataka",
            "Haryana Delhi & Chandigarh",
            "Kerala",
            "Orissa",
        ],
        "states": ["Karnataka", "Karnataka", "Haryana;Delhi;Chandigarh", "Kerala", "Odisha"],
    }
)
REFS: dict[str, Any] = {
    "imd_subdivisions": SUBDIVISIONS,
    "subdivision_aliases": pd.DataFrame({"alias": ["Odisha"], "canonical": ["Orissa"]}),
    "place_aliases": pd.DataFrame(
        {"alias": ["Orissa", "Azadpur"], "canonical": ["Odisha", "APMC Azadpur"]}
    ),
}


def _intent(dataset_id: str, places: list[str], operation: str = "lookup") -> QueryIntent:
    return QueryIntent.model_validate(
        {
            "action": "answer",
            "dataset_id": dataset_id,
            "indicator_ids": [],
            "place_mentions": places,
            "all_places_level": None,
            "period_mentions": [],
            "categories": {},
            "operation": operation,
            "order": None,
            "limit": None,
            "derivations": [],
            "changed_slots": [],
            "reason": None,
        }
    )


def _db(tmp_path: Path, name: str, rows: dict[str, list[Any]]) -> ReadOnlyDatabase:
    parquet = tmp_path / f"obs_{name}.parquet"
    pd.DataFrame(rows).to_parquet(parquet)
    return ReadOnlyDatabase({f"obs_{name}": parquet})


def _rain_db(tmp_path: Path) -> ReadOnlyDatabase:
    names = list(SUBDIVISIONS["subdivision"])
    return _db(
        tmp_path,
        "rain",
        {
            "dataset_version": ["v1"] * len(names),
            "geo_level": ["subdivision"] * len(names),
            "geo_code": [f"subdivision:{i}" for i in range(len(names))],
            "geo_name": names,
            "geo_vintage": ["imd"] * len(names),
        },
    )


def _district_db(tmp_path: Path) -> ReadOnlyDatabase:
    return _db(
        tmp_path,
        "dist",
        {
            "dataset_version": ["v1"] * 3,
            "geo_level": ["district"] * 3,
            "geo_code": [
                "district:bihar/aurangabad",
                "district:maharashtra/aurangabad",
                "district:bihar/patna",
            ],
            "geo_name": ["Aurangabad", "Aurangabad", "Patna"],
            "geo_state": ["Bihar", "Maharashtra", "Bihar"],
            "geo_vintage": ["2011"] * 3,
        },
    )


RAIN = {"dataset_id": "rain", "dataset_version": "v1", "geo_levels": ["subdivision"]}
DIST = {"dataset_id": "dist", "dataset_version": "v1", "geo_levels": ["district"]}


def _plan(intent: QueryIntent, dataset: dict[str, Any], db: ReadOnlyDatabase) -> Any:
    return resolve_plan(intent, dataset=dataset, indicators=[], db=db, refs=REFS, catalogue={})


# A1. State to IMD sub-division.


def test_a_state_split_into_sub_divisions_returns_one_row_each(tmp_path: Path) -> None:
    plan = _plan(_intent("rain", ["Karnataka"]), RAIN, _rain_db(tmp_path))
    assert [p.name for p in plan.places] == ["Coastal Karnataka", "North Interior Karnataka"]
    assert not plan.unresolved
    note = next(a.text for a in plan.assumptions if a.code == "SUBDIVISION")
    assert "no figure for Karnataka as a whole" in note and "one row each" in note


def test_a_sub_division_covering_several_states_is_used_and_said(tmp_path: Path) -> None:
    plan = _plan(_intent("rain", ["Delhi"]), RAIN, _rain_db(tmp_path))
    assert [p.name for p in plan.places] == ["Haryana Delhi & Chandigarh"]
    note = next(a.text for a in plan.assumptions if a.code == "SUBDIVISION")
    assert "also covers Haryana and Chandigarh" in note


def test_a_state_that_is_itself_a_sub_division_needs_no_mapping(tmp_path: Path) -> None:
    plan = _plan(_intent("rain", ["Kerala"]), RAIN, _rain_db(tmp_path))
    assert [p.name for p in plan.places] == ["Kerala"]
    assert not any(a.code == "SUBDIVISION" for a in plan.assumptions)


# A2. Former names and market aliases.


def test_odisha_finds_the_sub_division_stored_as_orissa(tmp_path: Path) -> None:
    plan = _plan(_intent("rain", ["Odisha"]), RAIN, _rain_db(tmp_path))
    assert [p.name for p in plan.places] == ["Orissa"] and not plan.unresolved
    assert any(a.code == "ALIAS" and "'Orissa'" in a.text for a in plan.assumptions)


def test_alias_candidates_keep_every_canonical_name() -> None:
    refs = {
        "place_aliases": {"Odisha": "Odisha State"},
        "subdivision_aliases": {"Odisha": "Orissa"},
    }
    assert alias_candidates("odisha", refs) == ["Odisha State", "Orissa"]


def test_a_market_alias_resolves_without_a_question(tmp_path: Path) -> None:
    db = _db(
        tmp_path,
        "mandi",
        {
            "dataset_version": ["v1"],
            "geo_level": ["market"],
            "geo_code": ["market:delhi/delhi/apmc_azadpur"],
            "geo_name": ["APMC Azadpur"],
            "geo_state": ["Delhi"],
            "geo_vintage": ["2011"],
        },
    )
    dataset = {"dataset_id": "mandi", "dataset_version": "v1", "geo_levels": ["market"]}
    plan = _plan(_intent("mandi", ["Azadpur"]), dataset, db)
    assert [p.name for p in plan.places] == ["APMC Azadpur"] and not plan.unresolved
    assert any(a.code == "ALIAS" for a in plan.assumptions)


# A3. Same-named districts.


def test_split_qualifier() -> None:
    assert split_qualifier("Aurangabad, Maharashtra") == ("Aurangabad", "Maharashtra")
    assert split_qualifier("Aurangabad (Bihar)") == ("Aurangabad", "Bihar")
    assert split_qualifier("Haryana Delhi & Chandigarh") == ("Haryana Delhi & Chandigarh", None)
    assert split_qualifier("Aurangabad district of Bihar") == ("Aurangabad", "Bihar")
    assert split_qualifier("Aurangabad district, Maharashtra") == ("Aurangabad", "Maharashtra")
    assert split_qualifier("NCT of Delhi") == ("NCT of Delhi", None)


def test_a_duplicate_district_without_a_state_is_asked_with_states(tmp_path: Path) -> None:
    plan = _plan(_intent("dist", ["Aurangabad"]), DIST, _district_db(tmp_path))
    assert not plan.places
    assert [(u.slot, u.options) for u in plan.unresolved] == [
        ("place", ["Aurangabad (Bihar)", "Aurangabad (Maharashtra)"])
    ]


@pytest.mark.parametrize(
    ("mentions", "code"),
    [
        (["Aurangabad", "Maharashtra"], "district:maharashtra/aurangabad"),
        (["Bihar", "Aurangabad"], "district:bihar/aurangabad"),
        (["Aurangabad, Maharashtra"], "district:maharashtra/aurangabad"),
        (["Aurangabad (Bihar)"], "district:bihar/aurangabad"),  # the clarification's option
        (["Aurangabad district of Maharashtra"], "district:maharashtra/aurangabad"),
        (["Patna district"], "district:bihar/patna"),
    ],
)
def test_a_named_state_chooses_the_district(tmp_path: Path, mentions: list[str], code: str) -> None:
    plan = _plan(_intent("dist", mentions), DIST, _district_db(tmp_path))
    assert [p.code for p in plan.places] == [code]
    assert not plan.unresolved


def test_a_level_word_after_a_duplicate_name_still_asks(tmp_path: Path) -> None:
    found = resolve_place("Aurangabad district", "dist", "district", REFS, _district_db(tmp_path))
    assert found.options == ["Aurangabad (Bihar)", "Aurangabad (Maharashtra)"]


def test_a_state_without_the_district_does_not_choose(tmp_path: Path) -> None:
    db = _district_db(tmp_path)
    found = resolve_place("Aurangabad", "dist", "district", REFS, db, state="Kerala")
    assert found.status == "unresolved" and len(found.options) == 2


def test_two_different_districts_stay_two_places(tmp_path: Path) -> None:
    plan = _plan(
        _intent("dist", ["Patna", "Aurangabad, Bihar"], "comparison"), DIST, _district_db(tmp_path)
    )
    assert [p.code for p in plan.places] == ["district:bihar/patna", "district:bihar/aurangabad"]


# On the published tables.


def _live_refs() -> dict[str, Any]:
    return {
        name: REFERENCE / f"{name}.csv"
        for name in ("imd_subdivisions", "place_aliases", "subdivision_aliases")
    }


@needs_data
def test_every_listed_duplicate_district_is_asked_or_chosen_on_its_table() -> None:
    rows = list(csv.DictReader((REFERENCE / "duplicate_districts.csv").open(encoding="utf-8")))
    assert rows
    for row in rows:
        dataset_id = row["dataset_id"]
        db = ReadOnlyDatabase({f"obs_{dataset_id}": PROCESSED / f"obs_{dataset_id}.parquet"})
        try:
            asked = resolve_place(row["district"], dataset_id, "district", _live_refs(), db)
            assert asked.status == "unresolved", row
            assert any(f"({row['state']})" in option for option in asked.options), row
            chosen = resolve_place(
                row["district"], dataset_id, "district", _live_refs(), db, state=row["state"]
            )
            assert chosen.place is not None, row
        finally:
            db.close()


@needs_data
@pytest.mark.parametrize(
    ("state", "count"), [("Karnataka", 3), ("Delhi", 1), ("Odisha", 1), ("Maharashtra", 4)]
)
def test_states_on_the_published_sub_division_table(state: str, count: int) -> None:
    from analyst.agents.context import published_catalogue

    dataset_id = "imd_subdivision_monthly_rainfall"
    table = published_catalogue()[dataset_id]
    db = ReadOnlyDatabase({f"obs_{dataset_id}": PROCESSED / f"obs_{dataset_id}.parquet"})
    try:
        plan = resolve_plan(
            _intent(dataset_id, [state]),
            dataset=table,
            indicators=[],
            db=db,
            refs=_live_refs(),
            catalogue={},
        )
    finally:
        db.close()
    assert len(plan.places) == count and not plan.unresolved


# A4. Urban/rural on a State question is defaulted to the total, not asked.


@needs_data
def test_a_state_question_without_area_uses_the_total_area() -> None:
    from analyst.agents.context import published_catalogue
    from analyst.agents.tool_nodes import indicators_of

    dataset_id = "nfhs5_state_factsheet"
    table = published_catalogue()[dataset_id]
    indicators = indicators_of(dict(table))
    intent = _intent(dataset_id, ["Kerala"]).model_copy(
        update={"indicator_ids": [indicators[0]["indicator_id"]]}
    )
    db = ReadOnlyDatabase({f"obs_{dataset_id}": PROCESSED / f"obs_{dataset_id}.parquet"})
    try:
        plan = resolve_plan(
            intent, dataset=table, indicators=indicators, db=db, refs=_live_refs(), catalogue={}
        )
    finally:
        db.close()
    assert not plan.unresolved
    assert [p.name for p in plan.places] == ["Kerala"]
    assert [v.casefold() for v in plan.categories["area"]] == ["total"]
    assert any(a.code == "TOTAL" for a in plan.assumptions)
