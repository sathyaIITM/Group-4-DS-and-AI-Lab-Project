"""The Laya training row keeps Kev's state and question text and moves the label."""

from analyst.decisions.kev_questions import QUESTIONS
from analyst.decisions.phase1 import domain_question, to_laya_row


def test_laya_row_matches_the_kev_question() -> None:
    record = {
        "state": {"catalogue": "1. t", "context": "No result table yet.", "user_message": "Hi"},
        "questions": {"domain": {**domain_question(), "label": "other"}},
        "_meta": {"id": "x1"},
    }
    row = to_laya_row(record)
    assert row["expected"] == {"domain": "other"}
    assert "label" not in row["questions"]["domain"]
    assert row["questions"]["domain"]["criteria"] == QUESTIONS["domain"][1]
    assert row["state"] == record["state"]
    assert "label" in record["questions"]["domain"]  # the input record is not changed
