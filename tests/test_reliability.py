"""Reliability fixes from the test ladder of 19 November: token refresh, rate limits, id repair."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from analyst.contracts import QueryIntent
from analyst.inference import llm
from analyst.inference.intent import repair_indicator_ids


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.text = ""

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "model": "m",
        }


def _request() -> llm.ChatRequest:
    return llm.ChatRequest("system", "user", "m", 0.0, 10, None, None)


def test_an_expired_token_is_refreshed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = [401, 200]
    tokens = iter(["old", "new"])
    used: list[str] = []

    def post(*_a: Any, headers: dict[str, str], **_k: Any) -> FakeResponse:
        used.append(headers["Authorization"])
        return FakeResponse(statuses.pop(0))

    monkeypatch.setattr(httpx, "post", post)
    cleared: list[bool] = []
    monkeypatch.setattr(llm, "clear_token", lambda: cleared.append(True))
    send = llm.http_transport("https://x", lambda: next(tokens), 5)
    send(_request())
    assert used == ["Bearer old", "Bearer new"] and cleared == [True]


def test_a_rate_limit_is_a_retryable_rate_limit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: FakeResponse(429))
    send = llm.http_transport("https://x", lambda: "t", 5)
    with pytest.raises(llm.RateLimitedError):
        send(_request())
    assert issubclass(llm.RateLimitedError, llm.TransientError)


def test_the_token_cache_uses_wall_clock_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # The monotonic clock stops while a Mac sleeps; the cache must age by wall-clock time.
    fetched: list[int] = []

    def fetch() -> str:
        fetched.append(1)
        return f"t{len(fetched)}"

    monkeypatch.setattr(llm, "_fetch_gcloud_token", fetch)
    llm.clear_token()
    clock = [1_000_000.0]
    monkeypatch.setattr(llm.time, "time", lambda: clock[0])
    llm.gcloud_token()
    clock[0] += llm.TOKEN_TTL_S + 1  # an hour passes, asleep or not
    llm.gcloud_token()
    assert len(fetched) == 2
    llm.clear_token()


def _intent(ids: list[str]) -> QueryIntent:
    return QueryIntent.model_validate(
        {
            "action": "answer",
            "dataset_id": "nfhs",
            "indicator_ids": ids,
            "place_mentions": [],
            "all_places_level": None,
            "period_mentions": [],
            "categories": {},
            "operation": "lookup",
            "order": None,
            "limit": None,
            "derivations": [],
            "changed_slots": [],
            "reason": None,
        }
    )


RETRIEVED = {
    "indicators": [
        {"dataset_id": "nfhs", "indicator_id": "n_children_who_have_received_bcg_4564c661"},
        {"dataset_id": "nfhs", "indicator_id": "n_women_anaemic_bde2c54c"},
        {"dataset_id": "other", "indicator_id": "x_women_anaemic_99999999"},
    ]
}


def test_a_miscopied_id_is_repaired_by_its_hash_suffix() -> None:
    # Dev ladder, 19 Nov: "..._who_received_bcg_4564c661" for "..._who_have_received_bcg_...".
    fixed = repair_indicator_ids(_intent(["n_children_who_received_bcg_4564c661"]), RETRIEVED)
    assert fixed.indicator_ids == ["n_children_who_have_received_bcg_4564c661"]


def test_an_id_without_a_unique_hash_match_is_left_for_validation() -> None:
    unknown = _intent(["n_something_else_12345678"])
    assert repair_indicator_ids(unknown, RETRIEVED).indicator_ids == unknown.indicator_ids
    other_table = _intent(["x_women_anaemic_99999999"])  # the hash belongs to another table
    assert repair_indicator_ids(other_table, RETRIEVED).indicator_ids == [
        "x_women_anaemic_99999999"
    ]


def test_no_guidance_card_tells_the_model_to_ask_the_user() -> None:
    # Dev ladder, 19 Nov: a card saying a bare year should be asked about overrode design rule
    # D7, and v1 and v2 asked for periods that code supplies. Whether to clarify is decided by
    # the intent rules and code; cards state facts.
    import json
    import re
    from pathlib import Path

    from analyst.agents.state import RagPaths

    cards = json.loads(Path(RagPaths().cards).read_text(encoding="utf-8"))["cards"]
    asking = re.compile(r"\b(ask|clarify with)\s+(which|whether|the user|for)\b", re.IGNORECASE)
    offending = [c["id"] for c in cards if asking.search(c["body"])]
    assert offending == []


def test_every_verified_example_follows_the_sql_prompt_rules() -> None:
    # Dev ladder, 19 Nov: 22 of 26 v1 examples left out the implausible-value filter, 20 filtered
    # periods by label and none selected the required columns; the SQL prompt says to follow the
    # examples, so v2 met two conflicting instructions. Examples are part of the specification.
    import json
    import re
    from pathlib import Path

    import sqlglot
    from sqlglot import exp

    from analyst.agents.state import RagPaths

    path = Path(RagPaths().examples)
    examples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    required = {"geo_name", "period_label", "indicator_id", "value", "unit"}
    problems = []
    for example in examples:
        sql = example["sql"]
        tree = sqlglot.parse_one(sql, read="duckdb")
        selected = {s.alias_or_name for s in tree.expressions}
        if not required <= selected:
            problems.append(f"{example['id']}: missing columns {sorted(required - selected)}")
        if (
            "quality_flag <> 'implausible'" not in sql
            and "quality_flag != 'implausible'" not in sql
        ):
            problems.append(f"{example['id']}: no implausible-value filter")
        if re.search(r"period_label\s*(=|IN\b|BETWEEN)", sql):
            problems.append(f"{example['id']}: periods filtered by label")
        if any(isinstance(n, (exp.Round, exp.Div)) for n in tree.walk()):
            problems.append(f"{example['id']}: a derivation computed in SQL")
    assert problems == []
