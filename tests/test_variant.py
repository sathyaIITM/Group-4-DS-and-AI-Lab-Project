"""The `jev_routing` variant: routing on Jev with the LLM as fallback, without a new version."""

from __future__ import annotations

from typing import Any

import pytest

from analyst.agents.state import RunConfig
from analyst.decisions.router import Backends, RouterConfig, RouterContext, route
from analyst.decisions.system_one import ChoiceAnswer, TimedChoice


def test_the_variant_replaces_the_routing_chains_of_v1() -> None:
    plain = RouterConfig.from_files("v1")
    jev = RouterConfig.from_files("v1", variant="jev_routing")
    assert plain.chains["tool"] == ["llm"] and plain.chains["domain"] == ["llm"]
    assert jev.chains["tool"] == ["jev", "llm"] and jev.chains["domain"] == ["jev", "llm"]


def test_v2_routes_on_jev_with_the_llm_as_fallback() -> None:
    # 19 Nov: v2 adds verified examples and moves tool and domain to Jev.
    for version in ("v2", "v3"):
        chains = RouterConfig.from_files(version).chains
        assert chains["tool"] == ["jev", "llm"] and chains["domain"] == ["jev", "llm"]


def test_an_unknown_variant_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown variant"):
        RouterConfig.from_files("v2", variant="nope")
    with pytest.raises(ValueError, match="unknown variant"):
        RunConfig.from_files("v2", variant="nope")


def test_the_run_config_records_the_variant() -> None:
    assert RunConfig.from_files("v1", variant="jev_routing").variant == "jev_routing"
    assert RunConfig.from_files("v1").variant is None


def test_jev_needs_its_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from analyst.agents.t3_nodes import jev_client

    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        jev_client()


class FakeJev:
    """Answers every choice question with its first option at probability 0.9."""

    def __init__(self, labels: dict[str, str]) -> None:
        self.labels = labels
        self.calls = 0

    def ask_choice(self, state: Any, questions: dict[str, Any]) -> TimedChoice:
        self.calls += 1
        name = next(iter(questions))
        label = self.labels[name]
        options = list(questions[name].criteria)
        probs = {o: (0.9 if o == label else 0.1 / (len(options) - 1)) for o in options}
        answer = ChoiceAnswer(choice=label, confidence=0.9, probabilities=probs)
        return TimedChoice(answers={name: answer}, latency_s=0.01, input_tokens=700)


def test_routing_on_jev_makes_no_llm_call() -> None:
    from analyst.agents.state import Counters

    config = RouterConfig.from_files("v2")
    jev = FakeJev({"tool": "run_sql", "domain": "labour"})
    counters = Counters()
    result = route(
        "What was the unemployment rate in Kerala?",
        RouterContext(has_result=False),
        ["plfs_state_ur_usual_status: unemployment"],
        config,
        Backends(jev=jev, llm=None),
        counters,
    )
    assert (result.decision.final_tool, result.decision.final_domain) == ("run_sql", "labour")
    assert result.decision.tool.backend == "jev" and result.llm_calls == []
    assert jev.calls == 2 and counters.llm_calls == 0
