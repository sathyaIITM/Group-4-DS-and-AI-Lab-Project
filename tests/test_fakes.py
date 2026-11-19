"""Tests for the scripted fakes."""

from tests.fakes import FakeDecisionClient, FakeIndex, FakeLLM, FakeToolSet


def test_fake_llm_scripts_by_purpose() -> None:
    llm = FakeLLM({"intent": [{"dataset_id": "rain"}]})
    assert llm.complete("intent") == {"dataset_id": "rain"}
    assert len(llm.calls) == 1


def test_fake_decision_client() -> None:
    client = FakeDecisionClient({"tool": "run_sql"})
    assert client.decide("tool") == "run_sql"


def test_fake_index_respects_top_k() -> None:
    index = FakeIndex([1, 2, 3])
    assert index.search("rain", kind="table", k=2) == [1, 2]


def test_fake_tools_accept_payload() -> None:
    tools = FakeToolSet({"resolve": lambda payload: payload["value"] + 1})
    assert tools.call("resolve", {"value": 1}) == 2
