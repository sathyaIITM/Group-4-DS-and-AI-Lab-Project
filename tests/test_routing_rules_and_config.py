"""Routing rules (P7, P8), context retrieval (N5) and configuration loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analyst.agents.control_nodes import resolve_routing_decision, retrieve_context_and_examples
from analyst.agents.state import AnalystState, Limits, RagPaths, RunConfig
from analyst.agents.stubs import stub_routing

pytestmark = pytest.mark.usefixtures("agent_cwd")

SET = {"shortcut_threshold": 0.9, "candidate_min_score": 0.5}


def route(tool: str, domain: str = "other", p: float = 0.99, prior: str | None = None, **limits):
    state = AnalystState(
        routing=stub_routing(tool, domain, p),
        config=RunConfig(limits=Limits(**limits)),
        prior_result_ref=prior,
    )
    return resolve_routing_decision(state)["routing"]


def test_agent_yaml_thresholds_are_null() -> None:
    limits = RunConfig.from_files("v0").limits
    assert limits.candidate_min_score is None
    assert limits.routing_floor is None
    assert limits.shortcut_threshold is None
    assert limits.answer_threshold is None


def test_decline_shortcut_needs_all_three_conditions() -> None:
    assert route("decline_not_covered", **SET).branch == "decline"
    assert route("decline_not_covered", domain="labour", **SET).branch == "query"
    assert route("decline_not_covered", p=0.5, **SET).branch == "query"


def test_null_thresholds_switch_the_shortcuts_off() -> None:
    assert route("decline_not_covered").branch == "query"
    assert route("ask_clarification").branch == "query"


def test_early_clarification_only_when_confident() -> None:
    assert route("ask_clarification", p=0.95, **SET).branch == "clarify"
    assert route("ask_clarification", p=0.6, **SET).branch == "query"


def test_low_confidence_label_is_kept() -> None:
    decision = route("describe_table", p=0.2, **SET, routing_floor=0.5)
    assert decision.final_tool == "describe_table"
    assert decision.branch == "describe"


def test_explain_without_prior_result_becomes_a_search() -> None:
    assert route("explain_result").branch == "search"
    assert route("explain_result", prior="ev_1").branch == "explain"


def write_rag(tmp: Path) -> RagPaths:
    cards = {
        "cards": [
            {"id": "a", "dataset_id": "t1", "body": "x"},
            {"id": "b", "dataset_id": "t2", "body": "x"},
            {"id": "sop", "dataset_id": None, "body": "x"},
        ]
    }
    (tmp / "cards.json").write_text(json.dumps(cards))
    examples = [{"id": "e1", "dataset_id": "t1"}, {"id": "e2", "dataset_id": "t2"}]
    (tmp / "ex.jsonl").write_text("\n".join(json.dumps(e) for e in examples))
    return RagPaths(cards=str(tmp / "cards.json"), examples=str(tmp / "ex.jsonl"))


def retrieved(version: str, tmp: Path, rag: RagPaths | None = None) -> dict:
    state = AnalystState(
        catalogue_candidates=[{"dataset_id": "t1"}],
        config=RunConfig(version=version, rag=rag or write_rag(tmp)),
    )
    return retrieve_context_and_examples(state)["retrieved"]


def test_versions_add_cards_then_examples(tmp_path: Path) -> None:
    v0, v1, v2 = (retrieved(v, tmp_path) for v in ("v0", "v1", "v2"))
    assert (v0["cards"], v0["examples"]) == ([], [])
    assert v1["card_ids"] == ["a", "sop"] and v1["examples"] == []
    assert v2["card_ids"] == ["a", "sop"]
    assert v2["example_ids"] == ["e1"]


def test_context_has_the_shape_the_intent_prompt_reads(tmp_path: Path) -> None:
    got = retrieved("v2", tmp_path)
    for key in ("tables", "indicators", "categories", "cards", "examples"):
        assert key in got
    assert all(isinstance(c, str) for c in got["cards"])
    assert set(got["examples"][0]) == {"question", "sql"}


def test_v0_files_are_the_fallback_when_v1_files_are_absent(tmp_path: Path) -> None:
    rag = RagPaths(cards=str(tmp_path / "missing.json"), examples=str(tmp_path / "missing.jsonl"))
    got = retrieved("v2", tmp_path, rag)
    assert "sop_lookup" in got["card_ids"]


def test_from_files_hashes_configuration_and_prompts() -> None:
    config = RunConfig.from_files("v2")
    assert {"configs/agent.yaml", "configs/model.yaml", "configs/inference.yaml"} <= set(
        config.config_hashes
    )
    assert {"intent.v1", "sql.v1", "narrate.v1"} <= set(config.prompt_hashes)
    assert config.model_id.startswith("gemini")
    assert RunConfig.from_files("v2").config_hashes == config.config_hashes
