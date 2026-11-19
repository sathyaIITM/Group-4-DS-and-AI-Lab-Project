"""The API on the stub agent (no model call): ask, stream, and the history across turns."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("agent_cwd")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import app.api.main as api

    monkeypatch.setattr(api, "AGENT_LLM", "stub")
    return TestClient(api.app)


def test_health_reports_the_agent_mode(client: TestClient) -> None:
    for path in ("/healthz", "/api/healthz"):
        body = client.get(path).json()
        assert body["status"] == "ok" and body["llm"] == "stub"


def test_ask_returns_a_reply_and_starts_a_conversation(client: TestClient) -> None:
    body = client.post("/api/ask", json={"question": "Show monthly rainfall in Kerala"}).json()
    assert body["conversation_id"] and body["run_id"]
    assert body["outcome"] is not None
    assert body["trace"][0] == "receive_request"
    assert [t["question"] for t in body["history"]] == ["Show monthly rainfall in Kerala"]


def test_a_second_turn_sees_the_first_in_its_history(client: TestClient) -> None:
    first = client.post("/ask", json={"question": "Show monthly rainfall in Kerala"}).json()
    second = client.post(
        "/ask", json={"question": "And Odisha?", "conversation_id": first["conversation_id"]}
    ).json()
    assert second["conversation_id"] == first["conversation_id"]
    assert [t["question"] for t in second["history"]] == [
        "Show monthly rainfall in Kerala",
        "And Odisha?",
    ]
    history = client.get(f"/api/conversations/{first['conversation_id']}").json()["history"]
    assert len(history) == 2


def test_stream_sends_stages_then_the_answer(client: TestClient) -> None:
    with client.stream("POST", "/api/stream", json={"question": "Show rainfall in Kerala"}) as r:
        text = "".join(r.iter_text())
    names = [
        line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("event:")
    ]
    assert names[0] == "stage" and names[-2:] == ["answer", "done"]
    answer = next(
        json.loads(block.split("data:", 1)[1])
        for block in text.split("\r\n\r\n")
        if block.startswith("event: answer")
    )
    assert answer["run_id"] and answer["outcome"] is not None


def test_the_page_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200 and "India Data Analyst" in response.text


def test_an_empty_question_is_rejected(client: TestClient) -> None:
    assert client.post("/ask", json={"question": ""}).status_code == 422
