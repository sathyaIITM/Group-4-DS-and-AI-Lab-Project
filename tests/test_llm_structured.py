"""Tests for LlmClient.structured (design document Section 7)."""

import json

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


def test_output_token_cap_is_sent_per_purpose() -> None:
    client, transport = scripted_client(GOOD, GOOD)
    client.max_output_tokens = {"sql_repair": 512}
    client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=Counters())
    assert [r.max_tokens for r in transport.requests] == [512]


def test_configured_caps_cover_every_prompt() -> None:
    import yaml

    from analyst.inference.llm import MODEL_CONFIG
    from analyst.inference.prompts import PromptRegistry

    caps = yaml.safe_load(MODEL_CONFIG.read_text())["hosted_llm"]["max_output_tokens"]
    assert {p.purpose for p in PromptRegistry()} <= set(caps)
    assert all(isinstance(v, int) and v > 0 for v in caps.values())


# ---------------------------------------------------------------------------- thinking


def test_thinking_level_is_sent_and_recorded() -> None:
    client, transport = scripted_client(GOOD)
    client.thinking = {"sql_repair": "low"}
    _, record = client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=Counters())
    assert transport.requests[0].reasoning_effort == "low"
    assert record.thinking_level == "low"


def test_no_configured_level_sends_none() -> None:
    client, transport = scripted_client(GOOD)
    client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=Counters())
    assert transport.requests[0].reasoning_effort is None


def test_regeneration_uses_the_higher_level() -> None:
    client, _ = scripted_client()
    client.thinking = {"sql": "minimal"}
    client.thinking_on_regenerate = {"sql": "medium"}
    assert client.thinking_level("sql") == "minimal"
    assert client.thinking_level("sql", regenerate=True) == "medium"
    assert client.thinking_level("narrate", regenerate=True) is None


def test_level_moves_up_to_the_nearest_accepted() -> None:
    client, _ = scripted_client()
    client.model = "google/gemini-3.8-flash"
    client.thinking = {"route": "minimal", "sql": "high"}
    client.supported_levels = {"gemini-3.8-flash": ["low", "medium", "high"]}
    assert client.thinking_level("route") == "low"
    assert client.thinking_level("sql") == "high"
    client.supported_levels = {"gemini-3.8-flash": ["low"]}
    with pytest.raises(LlmError):
        client.thinking_level("sql")


def test_unknown_level_is_rejected() -> None:
    client, _ = scripted_client()
    client.thinking = {"sql": "max"}
    with pytest.raises(LlmError, match="unknown thinking level"):
        client.thinking_level("sql")


def test_configured_thinking_covers_every_prompt_and_is_valid() -> None:
    import yaml

    from analyst.inference.llm import MODEL_CONFIG, THINKING_ORDER
    from analyst.inference.prompts import PromptRegistry

    thinking = yaml.safe_load(MODEL_CONFIG.read_text())["hosted_llm"]["thinking"]
    levels = {**thinking["per_purpose"], **thinking["on_regenerate"]}
    assert {p.purpose for p in PromptRegistry()} <= set(thinking["per_purpose"])
    assert set(levels.values()) <= set(THINKING_ORDER)
    for accepted in thinking["supported_levels"].values():
        assert set(accepted) <= set(THINKING_ORDER)


def test_request_body_sets_thinking_one_way_only() -> None:
    from analyst.inference.llm import ChatRequest, request_body

    body = request_body(ChatRequest("s", "u", "google/m", 0.0, 512, "low"))
    assert body["reasoning_effort"] == "low" and body["max_tokens"] == 512
    assert "thinking_config" not in json.dumps(body) and "thinking_budget" not in json.dumps(body)
    assert "reasoning_effort" not in request_body(ChatRequest("s", "u", "m", 0.0))


def test_reply_reports_thinking_tokens_and_finish_reason() -> None:
    from analyst.inference.llm import parse_reply

    payload = {
        "model": "google/gemini-3.5-flash-lite-001",
        "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 512,
            "completion_tokens_details": {"reasoning_tokens": 480},
        },
    }
    reply = parse_reply(payload, "m", 10)
    assert (reply.reasoning_tokens, reply.finish_reason) == (480, "length")
    assert parse_reply({"choices": [{"message": {"content": ""}}]}, "m", 1).reasoning_tokens is None


def test_cost_counts_thinking_tokens_as_output() -> None:
    from analyst.inference.llm import ChatReply, billed_output_tokens

    reply = ChatReply(
        "{}", tokens_in=126, tokens_out=18, served_model="m", latency_ms=1, reasoning_tokens=490
    )
    assert billed_output_tokens(reply) == 508
    client, _ = scripted_client()
    assert client._cost(126, billed_output_tokens(reply)) == pytest.approx(
        (126 * 0.1 + 508 * 0.4) / 1e6
    )


def test_output_cap_adds_the_thinking_allowance() -> None:
    client, transport = scripted_client(GOOD)
    client.max_output_tokens = {"sql": 512, "sql_repair": 512}
    client.thinking = {"sql": "minimal", "sql_repair": "low"}
    client.thinking_on_regenerate = {"sql": "medium"}
    client.thinking_allowance = {"minimal": 0, "low": 1024, "medium": 2048}
    assert client.output_cap("sql", client.thinking_level("sql")) == 512
    assert client.output_cap("sql", client.thinking_level("sql", regenerate=True)) == 2560
    assert client.output_cap("narrate", "low") is None
    client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=Counters())
    assert transport.requests[0].max_tokens == 1536


def test_every_configured_level_has_an_allowance() -> None:
    import yaml

    from analyst.inference.llm import MODEL_CONFIG, THINKING_ORDER

    config = yaml.safe_load(MODEL_CONFIG.read_text())["hosted_llm"]
    assert set(config["thinking"]["allowance"]) == set(THINKING_ORDER)
    assert config["thinking"]["allowance"]["minimal"] == 0
    assert set(config["tiers"]) <= set(config["price_per_mtok"])


def test_from_config_ignores_llm_model_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from analyst.inference.llm import LlmClient

    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    client = LlmClient.from_config()
    assert client.model == "google/gemini-3.5-flash-lite"
    assert LlmClient.from_config(tier="large").model == "google/gemini-3.8-flash"


# ---------------------------------------------------------------------------- reply shape


def test_null_and_single_object_list_fields_are_repaired() -> None:
    from analyst.contracts.intent import QueryIntent
    from analyst.inference.llm import coerce_lists

    raw = {"derivations": None, "indicator_ids": {"x": 1}, "categories": None, "reason": None}
    fixed = coerce_lists(raw, QueryIntent)
    assert fixed["derivations"] == []
    assert fixed["indicator_ids"] == [{"x": 1}]  # wrapped; validation still judges the content
    assert fixed["categories"] is None  # not a list field: left for validation to reject


def test_intent_with_null_derivations_is_accepted() -> None:
    from analyst.contracts.intent import QueryIntent

    reply = {
        "action": "answer",
        "dataset_id": "d",
        "indicator_ids": ["i"],
        "place_mentions": [],
        "all_places_level": None,
        "period_mentions": [],
        "categories": {},
        "operation": "lookup",
        "order": None,
        "limit": None,
        "derivations": None,
        "changed_slots": None,
        "reason": None,
    }
    client, _ = scripted_client(reply)
    intent, record = client.structured(
        "intent",
        "intent",
        {"catalogue": {}, "question": "q", "context": {}, "prior_plan": None, "history": []},
        QueryIntent,
        counters=Counters(),
    )
    assert intent.derivations == [] and intent.changed_slots == []
    assert record.earlier_attempts == []


def test_schema_output_sends_an_inlined_schema() -> None:
    from analyst.contracts.intent import QueryIntent
    from analyst.inference.llm import ChatRequest, inline_schema, request_body

    schema = inline_schema(QueryIntent.model_json_schema())
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    assert schema["properties"]["derivations"]["type"] == "array"
    body = request_body(ChatRequest("s", "u", "m", 0.0, response_schema=schema))
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == schema
    client, transport = scripted_client(GOOD)
    client.schema_output = True
    client.structured("sql_repair", "sql_repair", VARS, SqlDraft, counters=Counters())
    assert transport.requests[0].response_schema is not None
