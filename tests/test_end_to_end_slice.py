"""End-to-end slice: ranking, checks and one case end to end with a stub decision client."""

from pathlib import Path
from typing import Any

import pandas as pd

from analyst.decisions.kev_questions import DOMAIN_OPTIONS
from analyst.decisions.system_one import ChoiceAnswer, TimedChoice
from analyst.pipelines import end_to_end_slice as slice_run
from analyst.tools.sql_runner import ReadOnlyDatabase

TABLES = [
    {
        "dataset_id": "rain",
        "title": "Rainfall by region",
        "domain": "rainfall",
        "publisher": "IMD",
        "licence": "GODL-India",
        "retrieved": "2026-10-23",
        "dataset_version": "1.0.0+x",
        "raw_sha256": "abc",
        "caveats": ["a caveat"],
    },
    {
        "dataset_id": "jobs",
        "title": "Unemployment by State",
        "domain": "labour",
        "publisher": "MoSPI",
        "licence": "GODL-India",
        "retrieved": "2026-10-23",
        "dataset_version": "1.0.0+y",
        "raw_sha256": "def",
        "caveats": [],
    },
]


class StubClient:
    """Stands in for a served Kev: always answers the same domain."""

    def __init__(self, domain: str) -> None:
        self.domain = domain

    def ask_choice(self, state: Any, questions: Any) -> TimedChoice:
        probabilities = dict.fromkeys(DOMAIN_OPTIONS, 0.01) | {self.domain: 0.93}
        answer = ChoiceAnswer(choice=self.domain, confidence=0.9, probabilities=probabilities)
        return TimedChoice(answers={"domain": answer}, latency_s=0.01)


def _database(tmp_path: Path) -> ReadOnlyDatabase:
    path = tmp_path / "rain.parquet"
    pd.DataFrame({"region": ["A", "B"], "mm": [100.5, 200.0]}).to_parquet(path)
    return ReadOnlyDatabase({"rain": path})


def test_ranking_puts_the_predicted_domain_first_and_removes_nothing() -> None:
    ranked = slice_run.rank_tables(TABLES, "labour")
    assert [t["dataset_id"] for t in ranked] == ["jobs", "rain"]
    for domain in ("multiple", "unspecified", "other"):
        assert {t["dataset_id"] for t in slice_run.rank_tables(TABLES, domain)} == {"rain", "jobs"}


def test_catalogue_text_numbers_each_table() -> None:
    assert slice_run.catalogue_text(TABLES).splitlines()[1] == "2. jobs: Unemployment by State"


def test_checks_flag_empty_truncated_and_stored_answer() -> None:
    ok = slice_run.check_result(["mm"], [(100.5,)], 100.5)
    assert ok["non_empty"] and ok["matches_stored_answer"] is True and not ok["truncated"]
    assert slice_run.check_result(["mm"], [(90.0,)], 100.5)["matches_stored_answer"] is False
    assert slice_run.check_result(["mm"], [], None)["non_empty"] is False
    flags = slice_run.check_result(
        ["v", "quality_flag"], [(1, "reported"), (2, "suppressed"), (3, "reported")], None
    )
    assert flags["quality_flags"] == {"reported": 2, "suppressed": 1}


def test_answer_text_only_uses_cells_of_the_result() -> None:
    text = slice_run.answer_text(["region", "mm"], [("A", 100.5), ("B", 200.0)])
    assert "region = A" in text and "mm = 100.5" in text
    assert slice_run.answer_text(["mm"], []) == "The query returned no rows."


def test_a_case_runs_end_to_end_and_records_the_stand_in(tmp_path: Path) -> None:
    case = slice_run.Case(
        "c1", "Rain in region A?", "SELECT mm FROM rain WHERE region = 'A'", "rain", 100.5
    )
    record = slice_run.run_case(case, TABLES, _database(tmp_path), StubClient("rainfall"), "stub")
    assert record["outcome"] == "answered"
    assert record["ranking"]["expected_rank"] == 1
    assert record["ranking"]["domain_matches_table"] is True
    assert record["checks"]["matches_stored_answer"] is True
    assert record["sql_source"] == slice_run.SQL_SOURCE
    assert record["evidence"]["dataset_version"] == "1.0.0+x"


def test_a_rejected_query_is_a_failure_not_an_answer(tmp_path: Path) -> None:
    case = slice_run.Case("c2", "Drop it", "DROP TABLE rain", "rain")
    record = slice_run.run_case(case, TABLES, _database(tmp_path), StubClient("rainfall"), "stub")
    assert record["outcome"] == "failed"
    assert record["cause"] == "SqlRejectedError"
    assert "answer" not in record
