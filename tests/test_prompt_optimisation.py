"""Tests for the GEPA set-up of the intent prompt (`analyst.models.prompt_optimisation`)."""

from pathlib import Path
from typing import Any

import pytest

from analyst.inference.prompts import PinnedPromptRegistry, PromptRegistry, load_prompt
from analyst.inference.scripted import scripted_client
from analyst.models import prompt_optimisation as po

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
needs_data = pytest.mark.skipif(
    not list(PROCESSED.glob("obs_*.parquet")), reason="published tables are not present"
)
PLFS = "plfs_state_ur_usual_status"


def _item(**changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "e2e-990",
        "question": "Unemployment rate in Kerala, 2019-20?",
        "prior_turns": [],
        "expected_action": "answer",
        "notes": "",
        "expected_places": [{"name": "Kerala", "level": "state"}],
        "expected_periods": [{"start": "2019-07-01", "end": "2020-06-30"}],
        "indicator_ids": ["ur_usual_ps_ss"],
        "gold_lineage": "rows",
        "clarify_slot": None,
    }
    item.update(changes)
    return item


def _record(**changes: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "intent_action": "answer",
        "plan_places": [{"name": "Kerala", "level": "state"}],
        "plan_all_places_level": None,
        "plan_periods": [{"start": "2019-07-01", "end": "2020-06-30", "label": "2019-20"}],
        "plan_indicators": ["ur_usual_ps_ss"],
        "clarify_slots_asked": [],
    }
    record.update(changes)
    return record


def test_candidate_prompt_keeps_catalogue_user_and_placeholders(tmp_path: Path) -> None:
    base = PromptRegistry().get("intent")
    instructions, tail = po.split_system(base.system)
    assert "{{catalogue}}" in tail and "{{catalogue}}" not in instructions
    prompt = po.candidate_prompt(base, "New rules.\nAlways do X.")
    assert prompt.prompt_id == "intent_gepa.v1"
    assert prompt.user == base.user and prompt.system.startswith("New rules.")
    assert prompt.system.endswith(tail)
    path = tmp_path / "intent_gepa.v1.md"
    path.write_text(prompt.text, encoding="utf-8")
    loaded = load_prompt(path)  # the written file is a valid prompt
    assert loaded.inputs == base.inputs and loaded.sha256 == prompt.sha256


def test_override_and_pinned_registries() -> None:
    base = PromptRegistry().get("intent")
    override = po.candidate_prompt(base, "Only this.")
    registry = po.OverrideRegistry({"intent": override})
    assert registry.get("intent") is override
    assert registry.get("sql").id == "sql"
    pinned = PinnedPromptRegistry({"intent": "intent.v8"})
    assert pinned.get("intent").prompt_id == "intent.v8"
    assert pinned.get("sql").prompt_id == PromptRegistry().get("sql").prompt_id
    with pytest.raises(Exception, match="intent_gepa"):
        PinnedPromptRegistry({"intent": "intent_gepa.v99"})


def test_eligible_and_split() -> None:
    items = [_item(id=f"e2e-{i}") for i in range(9)] + [
        _item(id="e2e-c1", expected_action="clarify"),
        _item(id="e2e-c2", expected_action="clarify"),
        _item(id="e2e-c3", expected_action="clarify"),
        _item(id="e2e-f", prior_turns=["earlier"]),
        _item(id="e2e-s", expected_action="search"),
    ]
    eligible = [i for i in items if po.eligible(i)]
    assert {i["id"] for i in eligible} == {i["id"] for i in items} - {"e2e-f", "e2e-s"}
    train, val = po.split_items(eligible)
    assert len(val) == 4 and len(train) == 8  # a third of each action, rounded
    assert po.split_items(eligible) == (train, val)  # deterministic


def test_score_plan() -> None:
    assert po.score_plan(_item(), _record())[0] == 1.0
    score, feedback = po.score_plan(_item(), _record(intent_action="decline", intent_reason="x"))
    assert score == 0.0 and "expected answer, got decline" in feedback
    score, feedback = po.score_plan(_item(), _record(plan_indicators=["lfpr"]))
    assert score == pytest.approx(2 / 3) and "Indicators" in feedback
    clarify = _item(expected_action="clarify", clarify_slot="place")
    assert (
        po.score_plan(clarify, _record(intent_action="clarify", clarify_slots_asked=["place"]))[0]
        == 1.0
    )
    assert (
        po.score_plan(clarify, _record(intent_action="clarify", clarify_slots_asked=["period"]))[0]
        == 0.0
    )


def test_adapter_evaluate_and_reflective_dataset() -> None:
    base = PromptRegistry().get("intent")
    seen: list[str] = []

    def fake_run(
        item: dict[str, Any], registry: Any, make_llm: Any, version: str
    ) -> dict[str, Any]:
        seen.append(registry.get("intent").system[:9])
        return (
            _record(cost_usd_est=0.001) if item["id"] == "ok" else _record(intent_action="decline")
        )

    adapter = po.IntentAdapter(base=base, make_llm=lambda: None, run=fake_run, workers=1)
    batch = adapter.evaluate([_item(id="ok"), _item(id="bad")], {po.COMPONENT: "Candidate"}, True)
    assert batch.scores == [1.0, 0.0] and seen == ["Candidate", "Candidate"]
    assert adapter.spent_usd == pytest.approx(0.001)
    data = adapter.make_reflective_dataset({}, batch, [po.COMPONENT])
    rows = data[po.COMPONENT]
    assert len(rows) == 2 and rows[1]["Feedback"].startswith("Score 0.00")
    assert set(rows[0]) == {"Inputs", "Generated Outputs", "Feedback"}


def test_brackets_round_trip_and_reflection_call() -> None:
    text = "Use <catalogue> and <context>, never </user_question>."
    assert po.from_brackets(po.to_brackets(text)) == text
    assert "<" not in po.to_brackets(text)
    llm, transport = scripted_client({"new_instruction": "Read [catalogue] first."})
    spent: list[float] = []
    reply = po.reflection_lm(llm, spent)("Improve: Use <catalogue>.")
    assert reply == "```\nRead <catalogue> first.\n```"
    assert "[catalogue]" in transport.calls[0][1] and len(spent) == 1


@needs_data
def test_run_intent_offline_with_a_scripted_reply() -> None:
    reply = {
        "action": "answer",
        "dataset_id": PLFS,
        "indicator_ids": ["ur_usual_ps_ss"],
        "place_mentions": ["Kerala"],
        "all_places_level": None,
        "period_mentions": ["2019-20"],
        "categories": {},
        "operation": "lookup",
        "order": None,
        "limit": None,
        "derivations": [],
        "changed_slots": [],
        "reason": None,
    }
    llm, _ = scripted_client(reply)
    record = po.run_intent(_item(), PromptRegistry(), lambda: llm, "v3")
    assert record["intent_action"] == "answer"
    assert record["plan_places"] == [{"name": "Kerala", "level": "state"}]
    assert record["plan_periods"][0]["start"] == "2019-07-01"
    assert po.score_plan(_item(), record)[0] == 1.0
