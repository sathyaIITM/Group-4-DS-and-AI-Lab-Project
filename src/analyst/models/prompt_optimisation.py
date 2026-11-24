"""GEPA optimisation of the intent prompt: agent version v3 (Milestone 5).

GEPA (the `gepa` library, which DSPy's `dspy.GEPA` optimiser wraps) evolves the text of a prompt
from scored runs and written feedback. Here it evolves one component: the instruction text of
the intent prompt's system section (`configs/prompts/intent.v9.md`, before the catalogue block).
The catalogue block, the user section and every placeholder stay fixed, so a candidate cannot
drop an input, and the provider's cache of the catalogue prefix still applies.

One evaluation of a candidate on one item runs three graph steps, as the agent does: catalogue
ranking and context retrieval (local, no model), intent extraction (one hosted-model call with
the candidate prompt), and deterministic resolution into a plan. The plan is scored against the
structured gold fields with the checks of scorer v3 (action, interpretation, clarification
slot), so the optimiser works toward the measure the evaluation uses. Items are dev items only
(never test items); follow-ups and describe/search items are left out, because their outcome is
not decided by the intent prompt alone.

Scores: 0 when the action is wrong; otherwise the share of the applicable checks that pass. The
feedback names each failed check with the gold and the agent's value; GEPA's reflection model
reads it to propose the next instruction.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, ConfigDict

from analyst.evaluation import scorer_v3
from analyst.inference.prompts import Prompt, PromptRegistry

COMPONENT = "intent_instructions"
CATALOGUE_SEGMENT = "<catalogue>\n{{catalogue}}\n</catalogue>"
ACTIONS = {"answer", "clarify", "decline"}


def split_system(system: str) -> tuple[str, str]:
    """Split a system section into the optimisable instructions and the fixed catalogue tail."""
    index = system.find(CATALOGUE_SEGMENT)
    if index < 0:
        raise ValueError("the intent prompt has no catalogue block to keep fixed")
    return system[:index].rstrip() + "\n", system[index:]


def prompt_text(base: Prompt, prompt_id: str, version: int, system: str) -> str:
    """The file text of a prompt that differs from `base` only in id, version and system."""
    header = "\n".join(
        [
            "---",
            f"id: {prompt_id}",
            f"version: {version}",
            f"purpose: {base.purpose}",
            f"inputs: [{', '.join(base.inputs)}]",
            f"output_schema: {base.output_schema}",
            "---",
        ]
    )
    return f"{header}\n## System\n{system.strip()}\n\n## User\n{base.user.strip()}\n"


def candidate_prompt(
    base: Prompt, instructions: str, prompt_id: str = "intent_gepa", version: int = 1
) -> Prompt:
    """The intent prompt with new instructions and the fixed catalogue tail and user section."""
    _, tail = split_system(base.system)
    system = instructions.rstrip() + "\n\n" + tail
    text = prompt_text(base, prompt_id, version, system)
    return dataclasses.replace(
        base,
        id=prompt_id,
        version=version,
        system=system,
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


class OverrideRegistry(PromptRegistry):
    """A prompt registry in which some unversioned ids resolve to given prompts."""

    def __init__(self, overrides: dict[str, Prompt], base: PromptRegistry | None = None) -> None:
        """Wrap `base` (the repository's prompts) with in-memory overrides."""
        self._base = base or PromptRegistry()
        self._overrides = overrides
        self._prompts = self._base._prompts

    def get(self, prompt_id: str) -> Prompt:
        """Return the override for an unversioned id, otherwise the repository's prompt."""
        return self._overrides.get(prompt_id) or self._base.get(prompt_id)


def eligible(item: dict[str, Any]) -> bool:
    """Dev items whose outcome the intent prompt decides: no follow-up, no describe or search."""
    return item.get("expected_action") in ACTIONS and not item.get("prior_turns")


def split_items(
    items: Sequence[dict[str, Any]], val_share: float = 1 / 3, seed: int = 0
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic train/validation split, stratified by expected action."""
    rng = random.Random(seed)  # noqa: S311 - reproducible split, not security
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for action in sorted(ACTIONS):
        group = sorted((i for i in items if i["expected_action"] == action), key=lambda i: i["id"])
        rng.shuffle(group)
        cut = round(len(group) * val_share)
        val += group[:cut]
        train += group[cut:]
    return train, val


def score_plan(item: dict[str, Any], record: dict[str, Any]) -> tuple[float, str]:
    """Score one intent-and-plan record against the item's gold; return score and feedback."""
    gold = item["expected_action"]
    got = record.get("intent_action")
    lines = [f"Question: {item['question']}"]
    if got != gold:
        reason = record.get("intent_reason") or "none given"
        lines.append(f"Wrong action: expected {gold}, got {got} (reason given: {reason}).")
        if item.get("notes"):
            lines.append(f"Why the expected action is right: {item['notes']}")
        return 0.0, "\n".join(lines)
    case = {**item, **record, "expected_action": gold}
    checks: dict[str, bool] = {}
    if gold == "answer" and item.get("gold_lineage") is not None:
        checks["places"] = scorer_v3._places_match(case)
        checks["periods"] = scorer_v3._periods_match(case)
        checks["indicators"] = scorer_v3._indicators_match(case)
    if gold == "clarify" and item.get("clarify_slot"):
        checks["clarify_slot"] = item["clarify_slot"] in (record.get("clarify_slots_asked") or [])
    if not checks:
        return 1.0, "\n".join([*lines, "Correct."])
    for name, ok in checks.items():
        if ok:
            continue
        if name == "places":
            lines.append(
                f"Places: expected {[p['name'] for p in item.get('expected_places') or []]}, "
                f"resolved {[p['name'] for p in record.get('plan_places') or []]} "
                f"(whole level: {record.get('plan_all_places_level')}); "
                f"mentions extracted {record.get('place_mentions')}."
            )
        elif name == "periods":
            lines.append(
                f"Periods: expected {item.get('expected_periods')}, resolved "
                f"{[p.get('label') for p in record.get('plan_periods') or []]}; "
                f"mentions extracted {record.get('period_mentions')}."
            )
        elif name == "indicators":
            lines.append(
                f"Indicators: expected {item.get('indicator_ids')}, chosen "
                f"{record.get('plan_indicators')}."
            )
        else:
            lines.append(
                f"Clarification: expected the missing slot {item['clarify_slot']}, the agent "
                f"asked for {record.get('clarify_slots_asked')}."
            )
    score = sum(checks.values()) / len(checks)
    if score == 1.0:
        lines.append("Correct.")
    return score, "\n".join(lines)


def run_intent(
    item: dict[str, Any], registry: PromptRegistry, make_llm: Callable[[], Any], version: str
) -> dict[str, Any]:
    """Retrieve, extract the intent with the given prompts and resolve: the agent's first steps."""
    from analyst.agents import control_nodes
    from analyst.agents.model_nodes import live_tool_nodes
    from analyst.agents.state import AnalystState, Counters, RunConfig
    from analyst.evaluation.e2e_eval import _interpretation_record
    from analyst.inference import intent

    state = AnalystState(question=item["question"], config=RunConfig.from_files(version))
    for step in (
        control_nodes.retrieve_catalogue_candidates,
        control_nodes.retrieve_context_and_examples,
    ):
        update = step(state)
        state = state.model_copy(update={k: v for k, v in update.items() if k != "events"})
    llm = make_llm()
    llm.registry = registry
    try:
        parsed, call = intent.extract_intent(
            state.question, state.retrieved, None, llm, Counters(), state.history
        )
    except Exception as error:  # an unparseable reply counts as a wrong action
        return {"intent_action": "error", "intent_reason": f"{type(error).__name__}: {error}"}
    state = state.model_copy(update={"intent": parsed})
    resolve = live_tool_nodes()["resolve_places_periods_units"]
    update = resolve(state)
    state = state.model_copy(update={k: v for k, v in update.items() if k != "events"})
    record = _interpretation_record(state)
    record.update(
        intent_action=parsed.action,
        intent_reason=parsed.reason,
        place_mentions=parsed.place_mentions,
        period_mentions=parsed.period_mentions,
        cost_usd_est=call.cost_usd_est or 0.0,
    )
    return record


@dataclasses.dataclass
class IntentAdapter:
    """GEPA adapter: evaluates intent-prompt candidates on dev items (see module docstring)."""

    base: Prompt
    make_llm: Callable[[], Any]
    version: str = "v3"
    workers: int = 2
    run: Callable[..., dict[str, Any]] = run_intent
    spent_usd: float = 0.0
    propose_new_texts: Any = None  # GEPA reads this attribute; None selects its default proposer

    def evaluate(
        self, batch: list[dict[str, Any]], candidate: dict[str, str], capture_traces: bool = False
    ) -> Any:
        """Run the candidate on a batch; return scores, outputs and (optionally) trajectories."""
        from gepa.core.adapter import EvaluationBatch

        prompt = candidate_prompt(self.base, candidate[COMPONENT])
        registry = OverrideRegistry({"intent": prompt})
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            records = list(
                pool.map(lambda item: self.run(item, registry, self.make_llm, self.version), batch)
            )
        scored = [score_plan(item, record) for item, record in zip(batch, records, strict=True)]
        self.spent_usd += sum(float(r.get("cost_usd_est") or 0.0) for r in records)
        trajectories = (
            [
                {"item": item, "record": record, "feedback": feedback}
                for item, record, (_, feedback) in zip(batch, records, scored, strict=True)
            ]
            if capture_traces
            else None
        )
        return EvaluationBatch(
            outputs=records, scores=[s for s, _ in scored], trajectories=trajectories
        )

    def make_reflective_dataset(
        self, candidate: dict[str, str], eval_batch: Any, components_to_update: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Per component, the inputs, the agent's intent and the feedback of each item."""
        rows = []
        for trace, score in zip(eval_batch.trajectories or [], eval_batch.scores, strict=False):
            record = trace["record"]
            rows.append(
                {
                    "Inputs": trace["item"]["question"],
                    "Generated Outputs": json.dumps(
                        {
                            "action": record.get("intent_action"),
                            "place_mentions": record.get("place_mentions"),
                            "period_mentions": record.get("period_mentions"),
                            "indicators": record.get("plan_indicators"),
                            "missing_slot": record.get("clarify_slots_asked"),
                        },
                        ensure_ascii=False,
                    ),
                    "Feedback": f"Score {score:.2f}. {trace['feedback']}",
                }
            )
        return dict.fromkeys(components_to_update, rows)


class ReflectReply(BaseModel):
    """Reply of the reflection prompt (`configs/prompts/reflect.v1.md`)."""

    model_config = ConfigDict(extra="forbid")

    new_instruction: str


# Tags the prompt renderer removes from variable values (prompts._DELIMITERS); the reflection
# request quotes the instructions, so they travel in bracket form and are restored afterwards.
TAGS = ("user_question", "context", "history", "catalogue")


def to_brackets(text: str) -> str:
    """Write the delimiter tags as [tag] and [/tag] so the renderer keeps them."""
    return re.sub(r"<(/?)(" + "|".join(TAGS) + r")>", r"[\1\2]", text)


def from_brackets(text: str) -> str:
    """Restore [tag] and [/tag] to the delimiter tags."""
    return re.sub(r"\[(/?)(" + "|".join(TAGS) + r")\]", r"<\1\2>", text)


def reflection_lm(llm: Any, spent: list[float]) -> Callable[[str | list[dict[str, Any]]], str]:
    """GEPA's reflection model on the project's client; replies in GEPA's ``` format."""
    from analyst.agents.state import Counters

    def call(prompt: str | list[dict[str, Any]]) -> str:
        """Send the reflection request; return the new instruction inside a fence."""
        text = (
            prompt
            if isinstance(prompt, str)
            else "\n\n".join(str(m.get("content", "")) for m in prompt)
        )
        reply, record = llm.structured(
            "reflect",
            "reflect",
            {"request": to_brackets(text)},
            ReflectReply,
            counters=Counters(),
            node="gepa_reflect",
        )
        spent.append(float(record.cost_usd_est or 0.0))
        new = re.sub(r"^```[a-z]*\n|\n?```$", "", reply.new_instruction.strip()).strip()
        return f"```\n{from_brackets(new)}\n```"

    return call
