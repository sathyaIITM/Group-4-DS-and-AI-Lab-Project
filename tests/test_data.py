"""Tests for src/analyst/data: contract, generic operations, configs, source rules, catalogue."""

from datetime import date

import pandas as pd
import pytest
from tests.data_fixtures import BUILDERS, approved, config, run

from analyst.data import ops
from analyst.data.config import ReadSection, load_all
from analyst.data.contract import EMPTY_VALUE_FLAGS, FLAG_RANK, Flag
from analyst.data.publish import build_catalogue_entry, build_dim_period
from analyst.data.source_rules import RULES, SourceRule, register

NFHS_READ = ReadSection(
    missing_markers={"": "missing_in_source", "*": "suppressed"},
    flag_patterns=[
        {"name": "parentheses", "pattern": r"^\((.*)\)$", "flag": "low_sample_estimate"}
    ],
    strip_chars=["*"],
)


def parse(values: list[str | None], read: ReadSection = NFHS_READ, rules: list[str] | None = None):
    series = pd.Series(values, dtype="string")
    return ops.parse_values(series, read, rules or [])


def test_flag_vocabulary_has_one_rank_per_flag_and_reported_is_lowest() -> None:
    assert len(FLAG_RANK) == len(Flag)
    assert FLAG_RANK[Flag.UNPARSED.value] == 0
    assert FLAG_RANK[Flag.REPORTED.value] == max(FLAG_RANK.values())
    assert {"unparsed", "missing_in_source", "suppressed"} == EMPTY_VALUE_FLAGS


def test_parse_values_markers_patterns_and_numbers() -> None:
    value, flag, rule = parse(["12.5", "1,020", "*", None, "(29.5)", "12.5*", "NR"])
    assert value.iloc[0] == 12.5
    assert value.iloc[1] == 1020
    assert flag.iloc[2] == "suppressed" and pd.isna(value.iloc[2])
    assert flag.iloc[3] == "missing_in_source"
    assert flag.iloc[4] == "low_sample_estimate" and value.iloc[4] == 29.5
    assert flag.iloc[5] is None and value.iloc[5] == 12.5  # footnote star stripped, value kept
    assert flag.iloc[6] == "unparsed" and pd.isna(value.iloc[6])  # unknown text is never guessed
    assert "pattern:parentheses" in rule.iloc[4]
    assert "parse_failed" in rule.iloc[6]


def test_source_rule_reads_minus_as_low_sample_and_only_when_named() -> None:
    value, flag, rule = parse(["-29.5", "-100"], rules=["nfhs5_minus_as_low_sample"])
    assert list(value) == [29.5, 100.0]
    assert set(flag) == {"low_sample_estimate"}
    assert "nfhs5_minus_as_low_sample" in rule.iloc[0]
    # Without the rule the same text is a negative number, which the range check then flags.
    plain, plain_flag, _ = parse(["-29.5"])
    assert plain.iloc[0] == -29.5 and plain_flag.iloc[0] is None


def test_every_registered_rule_has_evidence_and_is_used_by_a_config() -> None:
    used = {rule.id for c in load_all() for rule in c.rules}
    assert set(RULES) == used
    for rule in RULES.values():
        assert rule.evidence and rule.description and rule.observed_values > 0


def test_registering_a_rule_twice_is_refused() -> None:
    existing = RULES["nfhs5_minus_as_low_sample"]
    with pytest.raises(ValueError, match="already registered"):
        register(SourceRule(existing.id, "x", "x", 1, existing.fn))


def test_unit_from_label_uses_ordered_rules() -> None:
    rules = config("nfhs5_district_indicators").values.unit_rules
    assert ops.unit_from_label("Women who are literate (%)", rules, "unknown") == "percent"
    assert (
        ops.unit_from_label("Sex ratio (females per 1,000 males)", rules, "unknown")
        == "per_1000_males"
    )
    assert ops.unit_from_label("Expenditure per delivery (Rs.)", rules, "unknown") == "INR"
    assert ops.unit_from_label("Number of households surveyed", rules, "unknown") == "count"
    assert ops.unit_from_label("Something else", rules, "unknown") == "unknown"


def test_year_bounds_follow_the_stated_start_month() -> None:
    assert ops.survey_year_bounds(2017, 7) == (date(2017, 7, 1), date(2018, 6, 30))
    assert ops.survey_year_bounds(2023, 4) == (date(2023, 4, 1), date(2024, 3, 31))
    assert ops.survey_year_bounds(2017, 1) == (date(2017, 1, 1), date(2017, 12, 31))
    assert ops.month_end(2024, 2) == date(2024, 2, 29)


def test_dim_period_maps_days_to_calendar_fiscal_and_july_june_years() -> None:
    dim = build_dim_period("2024-03-30", "2024-07-02").set_index("date")
    assert dim.loc["2024-03-31", "fiscal_year"] == "2023-24"
    assert dim.loc["2024-04-01", "fiscal_year"] == "2024-25"
    assert dim.loc["2024-06-30", "jul_jun_year"] == "2023-24"
    assert dim.loc["2024-07-01", "jul_jun_year"] == "2024-25"
    assert dim.loc["2024-04-01", "calendar_year"] == 2024


def test_place_matching_distinguishes_exact_alias_total_and_unmatched() -> None:
    canonical = set(ops.load_reference("states"))
    names, status = ops.match_names(
        pd.Series(["Kerala", "Orissa", "All India", "Atlantis"]),
        canonical,
        ops.load_aliases(),
        {"All India"},
    )
    assert list(names) == ["Kerala", "Odisha", "All India", "Atlantis"]
    assert list(status) == ["exact", "alias", "exact", "unmatched"]


def test_alias_table_points_only_at_canonical_names() -> None:
    canonical = set(ops.load_reference("states"))
    assert set(ops.load_aliases().values()) <= canonical


def test_all_five_configs_load_and_name_distinct_tables() -> None:
    configs = load_all()
    assert len(configs) == 5
    assert len({c.view.table for c in configs}) == 5
    assert len({c.obs_table for c in configs}) == 5


@pytest.mark.parametrize("dataset_id", sorted(BUILDERS))
def test_catalogue_facts_come_from_the_data(dataset_id: str) -> None:
    frame = BUILDERS[dataset_id]()
    result = run(dataset_id, frame, approved(frame))
    assert not result.blocked, [i for i in result.review if i.severity == "block"]
    entry = build_catalogue_entry(result.config, result.obs, "abc")
    assert entry.rows == len(result.obs)
    assert entry.coverage_start <= entry.coverage_end
    assert sum(entry.flag_counts.values()) == entry.rows
    assert entry.indicators == result.obs["indicator_id"].nunique()
    assert entry.has_total_rows == (dataset_id == "plfs_state_ur_usual_status")
