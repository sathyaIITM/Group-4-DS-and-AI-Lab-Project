"""Tests for LlmClient.structured (design document Section 7)."""

import pytest

from analyst.contracts.sql import SqlDraft
from analyst.inference.llm import BudgetExhaustedError, LlmError, TransientError
from analyst.inference.scripted import Counters, scripted_client

VARS = {"sql": "SELECT", "statement": "x", "error": "e", "schema": "s"}
GOOD = {"sql": "SELECT 1", "statement": "one row"}


def test_valid_reply_is_parsed_and_recorded() -> None:
    client, transport = scripted_client(GOOD)
    counters = Counters()
    draft, record = client.structured(
        "sql_repair", "sql_repair", VARS, SqlDraft, counters=counters, node="bounded_sql_repair"
    )
    assert draft == SqlDraft(**GOOD)
    assert counters.llm_calls == 1
    assert record.parsed_ok and record.prompt_id == "sql_repair" and record.prompt_version == 1
    assert len(record.prompt_sha256) == 64
    assert record.cost_usd_est == pytest.approx((100 * 0.1 + 20 * 0.4) / 1e6)
    assert record.variables == VARS
    assert "## System" in record.rendered_prompt
    assert len(transport.calls) == 1


def test_bad_reply_is_retried_once() -> None:
    client, _ = scripted_client("not json", GOOD)
    counters = Counters()
    _, record = client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=counters)
    assert counters.llm_calls == 2
    assert record.retry_of == 0
    assert len(record.earlier_attempts) == 1
    assert not record.earlier_attempts[0].parsed_ok


def test_two_bad_replies_raise_with_both_records() -> None:
    client, _ = scripted_client({"sql": "x"}, TransientError("HTTP 503"))
    with pytest.raises(LlmError) as caught:
        client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=Counters())
    assert len(caught.value.records) == 2
    assert "ValidationError" in (caught.value.records[0].parse_error or "")


def test_fatal_provider_error_is_not_retried() -> None:
    client, transport = scripted_client(LlmError("HTTP 400: bad request"), GOOD)
    counters = Counters()
    with pytest.raises(LlmError):
        client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=counters)
    assert counters.llm_calls == 1
    assert len(transport.calls) == 1


def test_budget_is_checked_before_each_call() -> None:
    client, transport = scripted_client("not json", GOOD, max_llm_calls=1)
    counters = Counters()
    with pytest.raises(BudgetExhaustedError) as caught:
        client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=counters)
    assert counters.llm_calls == 1
    assert len(transport.calls) == 1
    assert len(caught.value.records) == 1


def test_validator_rejection_counts_as_a_parse_failure() -> None:
    client, _ = scripted_client({"sql": "DROP TABLE x", "statement": "s"}, GOOD)

    def select_only(draft: SqlDraft) -> None:
        if not draft.sql.upper().startswith("SELECT"):
            raise ValueError("not a SELECT")

    draft, record = client.structured(
        "sql_repair", "sql_repair", VARS, SqlDraft, counters=Counters(), validate=select_only
    )
    assert draft.sql == "SELECT 1"
    assert "not a SELECT" in (record.earlier_attempts[0].parse_error or "")
