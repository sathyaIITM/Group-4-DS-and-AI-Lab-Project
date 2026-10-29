"""Tests for the Kev record contract, the rule-based generator and the data checks."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from analyst.data.catalogue import load_catalogue
from analyst.data.kev_checks import normalise, run_checks, shingles, write_without
from analyst.data.kev_generate import IMD, PLFS, generate, write_splits
from analyst.decisions.kev_questions import (
    DOMAIN_OPTIONS,
    STATE_CHAR_LIMIT,
    TOOL_OPTIONS,
    KevRecord,
    KevState,
    RecordMeta,
    build_record,
    serving_questions,
)

CATALOGUE = Path("configs/catalogue.toml")


@pytest.fixture(scope="module")
def records() -> list[KevRecord]:
    return generate(load_catalogue(CATALOGUE), n_families=400, seed=7)


def _meta() -> RecordMeta:
    return RecordMeta(
        id="t-1",
        group_id="g",
        label_source="human",
        tool_rule="R6",
        domain_rule="M1",
        family="test",
        template_id="test.0",
        has_result=False,
        generator="test",
        seed=0,
    )


def test_record_round_trip_keeps_canonical_text() -> None:
    state = KevState(catalogue="1. t", context="No result table yet.", user_message="Hi")
    record = build_record(state, "run_sql", "labour", _meta())
    again = KevRecord.model_validate_json(record.to_json())
    assert again.tool == "run_sql"
    assert again.domain == "labour"
    assert '"_meta"' in record.to_json()


def test_record_rejects_altered_question_text() -> None:
    state = KevState(catalogue="1. t", context="No result table yet.", user_message="Hi")
    data = build_record(state, "run_sql", "labour", _meta()).model_dump(by_alias=True)
    data["questions"]["tool"]["instructions"] = "Pick a tool."
    with pytest.raises(ValidationError):
        KevRecord.model_validate(data)


def test_serving_questions_match_training_text() -> None:
    questions = serving_questions()
    assert questions["tool"]["criteria"] == TOOL_OPTIONS
    assert questions["domain"]["criteria"] == DOMAIN_OPTIONS
    assert all("label" not in q for q in questions.values())


def test_generation_is_deterministic() -> None:
    catalogue = load_catalogue(CATALOGUE)
    first = [r.to_json() for r in generate(catalogue, n_families=50, seed=3)]
    second = [r.to_json() for r in generate(catalogue, n_families=50, seed=3)]
    assert first == second


def test_every_option_is_generated(records: list[KevRecord]) -> None:
    assert {r.tool for r in records} == set(TOOL_OPTIONS)
    assert {r.domain for r in records} == set(DOMAIN_OPTIONS)


def test_states_fit_the_length_budget(records: list[KevRecord]) -> None:
    assert max(r.state.rendered_length() for r in records) <= STATE_CHAR_LIMIT


def _table_shown(record: KevRecord, table: str) -> bool:
    return table in record.state.catalogue


def test_rule_labels_follow_the_guide(records: list[KevRecord]) -> None:
    for r in records:
        rule, tags = r.meta.tool_rule, r.meta.tags
        if "by_removal" in tags:
            assert r.tool == "decline_not_covered"
            needed = PLFS if r.domain == "labour" else IMD
            assert not _table_shown(r, needed)
        if r.tool == "make_chart":
            assert r.meta.has_result
            assert r.state.context.startswith("A result table is available")
        if rule in {"R5", "R6"}:
            assert not r.meta.has_result
            needed = PLFS if r.domain == "labour" else IMD
            assert _table_shown(r, needed)
        if rule == "R1":
            assert (r.tool, r.domain) == ("decline_not_covered", "other")
        if rule == "R2":
            assert r.tool == "search_catalog"


def test_out_of_range_periods_are_outside_the_table() -> None:
    catalogue = load_catalogue(CATALOGUE)
    rainfall = catalogue.get(IMD)
    assert rainfall.period_range is not None
    assert all(int(y) > rainfall.period_range[1] for y in rainfall.out_of_range_periods)
    labour = catalogue.get(PLFS)
    assert not set(labour.out_of_range_periods) & set(labour.periods)


def test_splits_do_not_share_groups_or_messages(records: list[KevRecord]) -> None:
    split_of_group: dict[str, str] = {}
    split_of_text: dict[str, str] = {}
    for r in records:
        assert split_of_group.setdefault(r.meta.group_id, str(r.meta.split)) == r.meta.split
        text = normalise(r.state.user_message)
        assert split_of_text.setdefault(text, str(r.meta.split)) == r.meta.split


def test_normalise_maps_digits_only_when_asked() -> None:
    assert normalise("Rain in 2015?") == "rain in 0000"
    assert normalise("Rain in 2015?", map_digits=False) == "rain in 2015"
    assert shingles("abc") == frozenset({" abc "})


def test_checks_find_a_planted_duplicate(records: list[KevRecord], tmp_path: Path) -> None:
    write_splits(records, tmp_path, version=9)
    train = tmp_path / "train.v9.jsonl"
    lines = train.read_text().splitlines()
    copy = re.sub(r'"id":"gen1-\d+"', '"id":"planted"', lines[0])
    train.write_text("\n".join([*lines, copy]) + "\n")
    result = run_checks(tmp_path, version=9, shortcuts=False)
    assert "planted" in result.drop
    assert not any("conflicting" in e for e in result.errors)
    assert write_without(tmp_path, 9, {"planted"}) == 1


def test_multiple_domain_records_name_each_domain(records: list[KevRecord]) -> None:
    multiple = [r for r in records if r.domain == "multiple"]
    assert multiple
    for r in multiple:
        assert len(set(r.meta.domains)) >= 2
        assert "multiple" not in r.meta.domains
    for r in records:
        if r.meta.tool_rule == "R16":
            assert "plfs_state_ur_usual_status" in r.state.catalogue
            assert "imd_subdivision_monthly_rainfall" in r.state.catalogue


def test_decided_categories_carry_their_labels(records: list[KevRecord]) -> None:
    for r in records:
        if "multi_place" in r.meta.tags:
            assert r.tool == "run_sql"  # H6: list each sub-division, never aggregate
        if "lacking_group" in r.meta.tags:
            assert r.tool == "ask_clarification"  # H5
        if r.meta.tool_rule == "R14":
            assert r.tool == "ask_clarification"  # H11b
        if r.domain == "unspecified":
            assert (r.tool, r.meta.has_result) == ("ask_clarification", False)  # H2


def test_reader_tolerates_pasted_artefacts(tmp_path: Path) -> None:
    from analyst.data.kev_ingest import read_objects

    messy = tmp_path / "reply.jsonl"
    messy.write_text(
        '```json\n{"a": 1} {"a": 2}\n\\<escape>{"a": 3}\n```\n'
        '{"id": "x", "question_for_human": "Is "R3" right?", "axes": ["short"]}\n'
    )
    objects, problems = read_objects(messy)
    assert [o.get("a") for o in objects[:3]] == [1, 2, 3]
    assert objects[3]["question_for_human"] == 'Is "R3" right?'
    assert any("repaired" in p for p in problems)
