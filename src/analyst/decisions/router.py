"""Routing node functions: tool selection and domain (design document Sections 5 and 8).

`route` builds the router state exactly as the Kev training records are built (catalogue lines
of the candidates, `kev_questions.render_context`, at most `STATE_CHAR_LIMIT` characters) and
asks each decision on the first backend of its chain in `configs/inference.yaml`:

- v0-v3: one hosted-LLM call answers both decisions (prompt `route`, same options).
- v4 onward (phase 1): tool on Jev and domain on Kev, asked in parallel. A backend that fails
  hands the decision to the next one in its chain (`fallback=True`).

Kev's probabilities are temperature-scaled with the temperature in `configs/model.yaml`
(`calibrated=True`). `escalate` re-asks Jev when Kev's calibrated maximum probability falls
inside the escalation band; a band of nulls disables it.
"""

import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict

from analyst.contracts.decisions import DecisionRecord, RoutingDecision
from analyst.decisions.kev_questions import (
    QUESTIONS,
    STATE_CHAR_LIMIT,
    KevState,
    render_context,
)
from analyst.decisions.system_one import ChoiceQuestion, TimedChoice
from analyst.inference.llm import CallCounter, LlmCallRecord, LlmClient

ROOT = Path(__file__).resolve().parents[3]
INFERENCE_CONFIG = ROOT / "configs" / "inference.yaml"
MODEL_CONFIG = ROOT / "configs" / "model.yaml"

Backend = Literal["kev", "jev", "llm"]
DECISIONS: tuple[Literal["tool", "domain"], ...] = ("tool", "domain")
LOG = logging.getLogger(__name__)
Branch = Literal["query", "chart", "describe", "search", "explain", "clarify", "decline"]
BRANCH: dict[str, Branch] = {
    "run_sql": "query",
    "make_chart": "chart",
    "describe_table": "describe",
    "search_catalog": "search",
    "explain_result": "explain",
    "ask_clarification": "clarify",
    "decline_not_covered": "decline",
}


class ChoiceBackend(Protocol):
    """A System One endpoint (Kev served locally, Jev hosted); `SystemOneClient` fits."""

    def ask_choice(
        self, state: str | dict[str, Any], questions: dict[str, ChoiceQuestion]
    ) -> TimedChoice:
        """Ask choice questions about a state and return the answers with their latency."""
        ...


@dataclass
class RouterContext:
    """What the router knows about the conversation besides the message."""

    has_result: bool = False
    prior_turn: str | None = None
    previous_tool: str | None = None


@dataclass
class Band:
    """A probability band; decisions inside it escalate to the next backend."""

    low: float | None = None
    high: float | None = None

    def contains(self, p: float) -> bool:
        """Return True when a probability falls inside the band."""
        return self.low is not None and self.high is not None and self.low <= p < self.high


@dataclass
class RouterConfig:
    """Backends per decision, calibration temperatures and escalation bands for a version."""

    version: str
    chains: dict[str, list[Backend]]
    kev_temperature: float | None = None
    kev_revision: str | None = None
    jev_model: str | None = None
    bands: dict[str, Band] = field(default_factory=dict)

    @classmethod
    def from_files(
        cls,
        version: str,
        inference: Path = INFERENCE_CONFIG,
        model: Path = MODEL_CONFIG,
        variant: str | None = None,
    ) -> "RouterConfig":
        """Chains of `version`; a `variant` from `inference.yaml` replaces the chains it names."""
        inf = yaml.safe_load(inference.read_text(encoding="utf-8"))
        mod = yaml.safe_load(model.read_text(encoding="utf-8"))
        override: dict[str, list[Backend]] = {}
        if variant is not None:
            found = (inf.get("variants") or {}).get(variant)
            if found is None:
                raise ValueError(f"unknown variant {variant!r} in {inference}")
            override = dict(found)
        chains: dict[str, list[Backend]] = {}
        for decision in DECISIONS:
            per_version = inf["decisions"][decision]
            chains[decision] = list(
                override.get(decision) or per_version.get(version) or per_version.get("all") or []
            )
            if not chains[decision]:
                raise ValueError(f"no backend chain for {decision} in {version}")
        bands: dict[str, Band] = {
            d: Band(**(inf.get("escalation", {}).get(d) or {})) for d in DECISIONS
        }
        return cls(
            version=version,
            chains=chains,
            kev_temperature=mod["kev"].get("temperature"),
            kev_revision=mod["kev"].get("checkpoint") or mod["kev"].get("revision"),
            jev_model=mod["jev"].get("model"),
            bands=bands,
        )


@dataclass
class Backends:
    """Clients injected by the graph; a missing client counts as a failed backend."""

    kev: ChoiceBackend | None = None
    jev: ChoiceBackend | None = None
    llm: LlmClient | None = None


@dataclass
class RouteResult:
    """The routing decision, the state it was made on and any model calls."""

    decision: RoutingDecision
    state: KevState
    llm_calls: list[LlmCallRecord] = field(default_factory=list)


class LlmRouting(BaseModel):
    """Output of the `route` prompt."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    domain: str
    probabilities: dict[str, dict[str, float]] = {}


class BackendUnavailableError(RuntimeError):
    """Every backend in a decision's chain failed."""


# ---------------------------------------------------------------------------- state


def render_catalogue(candidate_lines: Sequence[str]) -> str:
    """Render candidate tables as a numbered list."""
    return "\n".join(f"{i}. {line}" for i, line in enumerate(candidate_lines, start=1))


def build_state(question: str, context: RouterContext, candidate_lines: Sequence[str]) -> KevState:
    """The router state; trailing candidates are dropped until it fits the length limit."""
    rendered_context = render_context(context.has_result, context.prior_turn, context.previous_tool)
    lines = list(candidate_lines)
    while True:
        state = KevState(
            catalogue=render_catalogue(lines), context=rendered_context, user_message=question
        )
        if state.rendered_length() <= STATE_CHAR_LIMIT or not lines:
            return state
        lines.pop()


# ---------------------------------------------------------------------------- backends


def _question(decision: str) -> ChoiceQuestion:
    """Return the canonical choice question for a decision."""
    instructions, criteria = QUESTIONS[decision]
    return ChoiceQuestion(instructions=instructions, criteria=criteria)


def scale(probabilities: dict[str, float], temperature: float | None) -> dict[str, float]:
    """Rescale probabilities with a calibration temperature."""
    labels = list(probabilities)
    p = np.clip(np.array([probabilities[x] for x in labels], float), 1e-12, 1.0)
    p = p / p.sum()
    if temperature is not None:
        logits = np.log(p) / temperature
        logits -= logits.max()
        p = np.exp(logits) / np.exp(logits).sum()
    return {x: float(v) for x, v in zip(labels, p, strict=True)}


def _ask_choice(
    backend: Backend,
    client: ChoiceBackend,
    decision: Literal["tool", "domain"],
    state: KevState,
    config: RouterConfig,
    fallback: bool,
) -> DecisionRecord:
    """Ask one decision of a choice backend and return the decision record."""
    started = time.perf_counter()
    answer = client.ask_choice(state.model_dump(), {decision: _question(decision)})
    raw = answer.answers[decision].probabilities
    temperature = config.kev_temperature if backend == "kev" else None
    probabilities = scale(raw, temperature)
    label = max(probabilities, key=lambda k: probabilities[k])
    if label not in QUESTIONS[decision][1]:
        raise ValueError(f"{backend} returned unknown {decision} label {label!r}")
    return DecisionRecord(
        decision=decision,
        backend=backend,
        model_revision=config.kev_revision if backend == "kev" else config.jev_model,
        label=label,
        probabilities=probabilities,
        calibrated=temperature is not None,
        temperature=temperature,
        escalated=False,
        fallback=fallback,
        latency_ms=int((time.perf_counter() - started) * 1000),
        cost_usd=None,
    )


def _ask_llm(
    llm: LlmClient, state: KevState, counters: CallCounter
) -> tuple[dict[str, DecisionRecord], LlmCallRecord]:
    """One call answers both decisions; labels outside the options are rejected and retried."""

    def check(reply: LlmRouting) -> None:
        """Check that every label in the model's reply is a valid option."""
        for decision in DECISIONS:
            if getattr(reply, decision) not in QUESTIONS[decision][1]:
                raise ValueError(f"{decision} {getattr(reply, decision)!r} is not an option")

    options = {
        f"{d}_options": "\n".join(f"- {k}: {v}" for k, v in QUESTIONS[d][1].items())
        for d in DECISIONS
    }
    reply, record = llm.structured(
        "route",
        "route",
        {
            "catalogue": state.catalogue,
            "context": state.context,
            "question": state.user_message,
            **options,
        },
        LlmRouting,
        counters=counters,
        validate=check,
        node="route_tool_and_domain",
    )
    records: dict[str, DecisionRecord] = {}
    for decision in DECISIONS:
        label = getattr(reply, decision)
        given = reply.probabilities.get(decision) or {}
        options_d = QUESTIONS[decision][1]
        probs = {k: max(float(given.get(k, 0.0)), 0.0) for k in options_d}
        if sum(probs.values()) <= 0 or max(probs, key=lambda k: probs[k]) != label:
            probs = {k: float(k == label) for k in options_d}  # verbalised scores unusable
        total = sum(probs.values())
        records[decision] = DecisionRecord(
            decision=decision,
            backend="llm",
            model_revision=record.model_version or llm.model,
            label=label,
            probabilities={k: v / total for k, v in probs.items()},
            calibrated=False,
            temperature=None,
            escalated=False,
            fallback=False,
            latency_ms=record.latency_ms,
            cost_usd=record.cost_usd_est,
        )
    return records, record


def _decide(
    decision: Literal["tool", "domain"],
    state: KevState,
    config: RouterConfig,
    backends: Backends,
    llm_answer: dict[str, DecisionRecord] | None,
) -> DecisionRecord | None:
    """First working choice backend of the chain; None means the LLM must answer."""
    for position, backend in enumerate(config.chains[decision]):
        if backend == "llm":
            if llm_answer is not None:
                record = llm_answer[decision]
                return record.model_copy(update={"fallback": position > 0})
            return None
        client = backends.kev if backend == "kev" else backends.jev
        if client is None:
            continue
        try:
            return _ask_choice(backend, client, decision, state, config, fallback=position > 0)
        except Exception as error:  # a failed backend hands over (or keeps Kev's answer)
            LOG.warning("%s backend failed on %s: %s", backend, decision, error)
            continue
    raise BackendUnavailableError(f"no backend answered the {decision} decision")


# ---------------------------------------------------------------------------- nodes


def route(
    question: str,
    context: RouterContext,
    candidate_lines: Sequence[str],
    config: RouterConfig,
    backends: Backends,
    counters: CallCounter,
) -> RouteResult:
    """`route_tool_and_domain`. Raises `BackendUnavailableError` or `LlmError` when no backend
    can answer; the graph then ends with `failed / backend_error`."""
    state = build_state(question, context, candidate_lines)
    llm_first = all(config.chains[decision][0] == "llm" for decision in DECISIONS)
    llm_answer: dict[str, DecisionRecord] | None = None
    calls: list[LlmCallRecord] = []
    if llm_first:
        if backends.llm is None:
            raise BackendUnavailableError("the LLM backend is not configured")
        llm_answer, call = _ask_llm(backends.llm, state, counters)
        calls.append(call)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            decision: pool.submit(_decide, decision, state, config, backends, llm_answer)
            for decision in DECISIONS
        }
        records = {decision: f.result() for decision, f in futures.items()}
    if any(r is None for r in records.values()):  # a chain fell through to the LLM
        if backends.llm is None:
            raise BackendUnavailableError("fallback to the LLM, which is not configured")
        llm_answer, call = _ask_llm(backends.llm, state, counters)
        calls.append(call)
        for decision in DECISIONS:
            if records[decision] is None:
                records[decision] = llm_answer[decision].model_copy(update={"fallback": True})
    tool, domain = records["tool"], records["domain"]
    if tool is None or domain is None:  # filled above; kept for the type checker
        raise BackendUnavailableError("routing produced no decision")
    return RouteResult(_routing(tool, domain), state, calls)


def _routing(tool: DecisionRecord, domain: DecisionRecord) -> RoutingDecision:
    """Combine tool and domain decisions into a routing decision."""
    return RoutingDecision(
        tool=tool,
        domain=domain,
        final_tool=tool.label,
        final_domain=domain.label,
        branch=BRANCH[tool.label],
    )


def escalate(
    routing: RoutingDecision,
    state: KevState,
    config: RouterConfig,
    jev: ChoiceBackend | None,
) -> RoutingDecision:
    """`escalate_to_jev`. Each Kev decision whose calibrated maximum probability lies inside
    its band is asked again on Jev; Jev's answer replaces it with `escalated=True`. If Jev
    fails, Kev's answer stands."""
    updated = {"tool": routing.tool, "domain": routing.domain}
    for decision in DECISIONS:
        record = updated[decision]
        band = config.bands.get(decision, Band())
        if (
            record.backend != "kev"
            or jev is None
            or not band.contains(max(record.probabilities.values()))
        ):
            continue
        try:
            answer = _ask_choice("jev", jev, decision, state, config, fallback=False)
        except Exception as error:  # a failed backend hands over (or keeps Kev's answer)
            LOG.warning("escalation to jev failed on %s: %s", decision, error)
            continue
        updated[decision] = answer.model_copy(
            update={"escalated": True, "latency_ms": record.latency_ms + answer.latency_ms}
        )
    return _routing(updated["tool"], updated["domain"])
