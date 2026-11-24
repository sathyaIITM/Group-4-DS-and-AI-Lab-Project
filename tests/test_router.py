"""Tests for the routing node functions (design document Sections 5 and 8)."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from analyst.decisions import router as r
from analyst.decisions.kev_questions import DOMAIN_OPTIONS, STATE_CHAR_LIMIT, TOOL_OPTIONS
from analyst.decisions.system_one import ChoiceAnswer, ChoiceQuestion, TimedChoice
from analyst.inference.scripted import Counters, scripted_client

LINE = "plfs_state_ur_usual_status: PLFS unemployment rate (%), by State/UT, 2017-18 to 2021-22"


@dataclass
class FakeBackend:
    answers: dict[str, dict[str, float]]
    fail: bool = False
    seen: list[Any] = field(default_factory=list)

    def ask_choice(self, state: Any, questions: dict[str, ChoiceQuestion]) -> TimedChoice:
        self.seen.append((state, list(questions)))
        if self.fail:
            raise RuntimeError("down")
        name = next(iter(questions))
        probs = self.answers[name]
        top = max(probs, key=lambda k: probs[k])
        answer = ChoiceAnswer(choice=top, confidence=probs[top], probabilities=probs)
        return TimedChoice(answers={name: answer}, latency_s=0.01)


def _probs(options: dict[str, str], top: str, p: float) -> dict[str, float]:
    rest = (1 - p) / (len(options) - 1)
    return {k: (p if k == top else rest) for k in options}


def _config(version: str = "v4", **kw: Any) -> r.RouterConfig:
    config = r.RouterConfig.from_files(version)
    for key, value in kw.items():
        setattr(config, key, value)
    return config


LLM_REPLY = {
    "tool": "run_sql",
    "domain": "labour",
    "probabilities": {
        "tool": _probs(TOOL_OPTIONS, "run_sql", 0.8),
        "domain": _probs(DOMAIN_OPTIONS, "labour", 0.9),
    },
}


def test_state_matches_training_rendering_and_fits_the_limit() -> None:
    state = r.build_state("Unemployment in Bihar?", r.RouterContext(), [LINE] * 30)
    assert state.catalogue.startswith(f"1. {LINE}")
    assert state.context == "No result table yet."
    assert state.rendered_length() <= STATE_CHAR_LIMIT
    assert state.catalogue.count("\n") < 29  # trailing candidates dropped


def test_v0_routes_with_one_llm_call() -> None:
    llm, transport = scripted_client(LLM_REPLY)
    counters = Counters()
    result = r.route(
        "Unemployment in Bihar?",
        r.RouterContext(),
        [LINE],
        _config("v0"),
        r.Backends(llm=llm),
        counters,
    )
    d = result.decision
    assert (d.final_tool, d.final_domain, d.branch) == ("run_sql", "labour", "query")
    assert d.tool.backend == d.domain.backend == "llm"
    assert counters.llm_calls == 1 and len(result.llm_calls) == 1
    assert "<user_question>\nUnemployment in Bihar?\n</user_question>" in transport.calls[0][1]


def test_v4_uses_jev_for_tool_and_kev_for_domain_with_temperature() -> None:
    jev = FakeBackend({"tool": _probs(TOOL_OPTIONS, "describe_table", 0.7)})
    kev = FakeBackend({"domain": _probs(DOMAIN_OPTIONS, "labour", 0.9)})
    result = r.route(
        "What columns?",
        r.RouterContext(),
        [LINE],
        _config(kev_temperatures={"domain": 2.0}),
        r.Backends(kev=kev, jev=jev),
        Counters(),
    )
    d = result.decision
    assert (d.tool.backend, d.domain.backend) == ("jev", "kev")
    assert d.branch == "describe"
    assert d.domain.calibrated and d.domain.temperature == 2.0
    assert d.domain.probabilities["labour"] < 0.9  # T > 1 softens
    assert jev.seen[0][1] == ["tool"] and kev.seen[0][1] == ["domain"]
    assert jev.seen[0][0] == result.state.model_dump()


def test_failed_backend_hands_over_to_the_next() -> None:
    kev = FakeBackend({}, fail=True)
    jev = FakeBackend(
        {
            "tool": _probs(TOOL_OPTIONS, "run_sql", 0.6),
            "domain": _probs(DOMAIN_OPTIONS, "labour", 0.9),
        }
    )
    d = r.route(
        "x", r.RouterContext(), [LINE], _config(), r.Backends(kev=kev, jev=jev), Counters()
    ).decision
    assert d.domain.backend == "jev" and d.domain.fallback  # Kev down: Jev answers the domain
    assert d.tool.backend == "jev" and not d.tool.fallback


def test_chain_falls_through_to_the_llm() -> None:
    llm, _ = scripted_client(LLM_REPLY)
    counters = Counters()
    d = r.route("x", r.RouterContext(), [LINE], _config(), r.Backends(llm=llm), counters).decision
    assert d.tool.backend == d.domain.backend == "llm"
    assert d.tool.fallback and d.domain.fallback
    assert counters.llm_calls == 1  # one call serves both decisions


def test_no_backend_raises() -> None:
    with pytest.raises(r.BackendUnavailableError):
        r.route("x", r.RouterContext(), [LINE], _config(), r.Backends(), Counters())


def test_unusable_llm_probabilities_become_one_hot() -> None:
    reply = {**LLM_REPLY, "probabilities": {}}
    llm, _ = scripted_client(reply)
    d = r.route(
        "x", r.RouterContext(), [LINE], _config("v0"), r.Backends(llm=llm), Counters()
    ).decision
    assert d.tool.probabilities["run_sql"] == 1.0


def test_llm_label_outside_the_options_is_retried() -> None:
    llm, _ = scripted_client({**LLM_REPLY, "tool": "run_query"}, LLM_REPLY)
    counters = Counters()
    d = r.route(
        "x", r.RouterContext(), [LINE], _config("v0"), r.Backends(llm=llm), counters
    ).decision
    assert d.final_tool == "run_sql" and counters.llm_calls == 2


def test_escalation_inside_the_band_only() -> None:
    jev = FakeBackend(
        {
            "tool": _probs(TOOL_OPTIONS, "run_sql", 0.9),
            "domain": _probs(DOMAIN_OPTIONS, "health", 0.95),
        }
    )
    kev = FakeBackend({"domain": _probs(DOMAIN_OPTIONS, "labour", 0.55)})
    config = _config(bands={"domain": r.Band(0.0, 0.6), "tool": r.Band()})
    result = r.route(
        "x", r.RouterContext(), [LINE], config, r.Backends(kev=kev, jev=jev), Counters()
    )
    escalated = r.escalate(result.decision, result.state, config, jev)
    assert escalated.domain.escalated and escalated.final_domain == "health"
    assert not escalated.tool.escalated  # tool came from Jev already
    no_band = _config(bands={"domain": r.Band(), "tool": r.Band()})
    unchanged = r.escalate(result.decision, result.state, no_band, jev)  # null band
    assert unchanged == result.decision


def test_v4_configuration_from_files() -> None:
    config = r.RouterConfig.from_files("v4")
    assert config.chains["domain"] == ["kev", "jev", "llm"]
    assert config.chains["tool"] == ["jev", "llm"]  # the ep3 adapter knows only the domain
    assert config.kev_revision == "ep3"
    assert config.temperature_for("domain") == pytest.approx(3.7634, abs=1e-4)
    assert config.temperature_for("tool") is None  # set only after the phase 2 tool gate
    band = config.bands["domain"]
    assert band.contains(0.30) and not band.contains(0.45) and not band.contains(0.9)
    assert config.bands["tool"].low is None


def test_v4_escalates_a_low_confidence_domain_to_jev() -> None:
    config = r.RouterConfig.from_files("v4")
    flat = {k: 1 / len(DOMAIN_OPTIONS) for k in DOMAIN_OPTIONS}  # max well below the threshold
    flat["labour"] += 0.01
    kev = FakeBackend({"domain": flat})
    jev = FakeBackend(
        {
            "tool": _probs(TOOL_OPTIONS, "run_sql", 0.8),
            "domain": _probs(DOMAIN_OPTIONS, "health", 0.9),
        }
    )
    result = r.route(
        "x", r.RouterContext(), [LINE], config, r.Backends(kev=kev, jev=jev), Counters()
    )
    assert result.decision.domain.backend == "kev"
    updated = r.escalate(result.decision, result.state, config, jev)
    assert updated.domain.backend == "jev" and updated.domain.escalated
    assert updated.final_domain == "health"


def test_kev_client_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from analyst.agents.model_nodes import kev_client

    monkeypatch.setenv("KEV_BASE_URL", "http://127.0.0.1:9999")
    monkeypatch.delenv("KEV_API_KEY", raising=False)
    client = kev_client()
    assert str(client._client.base_url).startswith("http://127.0.0.1:9999")
    assert client._model == "kev-latest"
    monkeypatch.delenv("KEV_BASE_URL")
    assert str(kev_client()._client.base_url).startswith("http://127.0.0.1:8009")


def test_kev_temperature_per_decision() -> None:
    tool_raw = _probs(TOOL_OPTIONS, "run_sql", 0.9)
    domain_raw = _probs(DOMAIN_OPTIONS, "labour", 0.9)
    kev = FakeBackend({"tool": tool_raw, "domain": domain_raw})
    config = _config(
        kev_temperature=None,
        kev_temperatures={"tool": 1.5, "domain": 3.0},
        chains={"tool": ["kev", "jev", "llm"], "domain": ["kev", "jev", "llm"]},
    )
    d = r.route("x", r.RouterContext(), [LINE], config, r.Backends(kev=kev), Counters()).decision
    assert d.tool.temperature == 1.5 and d.domain.temperature == 3.0
    assert d.tool.probabilities == pytest.approx(r.scale(tool_raw, 1.5))
    assert d.domain.probabilities == pytest.approx(r.scale(domain_raw, 3.0))


def test_kev_temperature_forms_in_model_yaml() -> None:
    assert r._kev_temperatures(2.5) == {"kev_temperature": 2.5}
    assert r._kev_temperatures(None) == {"kev_temperature": None}
    both = r._kev_temperatures({"domain": 3.0, "tool": None})
    assert both == {"kev_temperatures": {"domain": 3.0, "tool": None}}
    single = r.RouterConfig(version="v4", chains={}, kev_temperature=2.0)
    assert single.temperature_for("tool") == single.temperature_for("domain") == 2.0
    with pytest.raises(ValueError, match="unknown decisions"):
        r._kev_temperatures({"coverage": 1.0})
