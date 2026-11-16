"""Hosted LLM client over an OpenAI-compatible chat-completions endpoint.

Two entry points:

- `json_call(purpose, system, user)`: one JSON call with raw prompts (Milestone 3 proof of
  concept and v0 evaluation; unchanged).
- `structured(purpose, prompt_id, variables, schema, *, counters)`: the agent's call (design
  document Section 7). It renders a registered prompt, counts the call against the run's budget
  before sending it, validates the reply against a Pydantic schema, retries once on a parse,
  validation or transient error, and returns the parsed model with an `LlmCallRecord` whose
  fields are the `llm_calls` columns of the run log (Section 9).

Providers (`configs/model.yaml`, `hosted_llm.provider`):

- `ai_studio`: Google AI Studio's OpenAI-compatible endpoint with `LLM_API_KEY`.
- `vertex`: Vertex AI's OpenAI-compatible endpoint for project `GOOGLE_CLOUD_PROJECT` in
  `hosted_llm.location`, authenticated by `gcloud auth application-default print-access-token`
  (no key files; T4 document Section 12). Model ids take the `google/` prefix there.
"""

import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from analyst.inference.prompts import Prompt, PromptRegistry

GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
MODEL_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "model.yaml"
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
USER_AGENT = "india-analyst-agent/0.1"

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LlmError(RuntimeError):
    """The model could not be reached or did not return valid JSON."""

    def __init__(self, message: str, records: list["LlmCallRecord"] | None = None) -> None:
        super().__init__(message)
        self.records = records or []


class BudgetExhaustedError(LlmError):
    """The run's LLM-call budget is spent; the call was not sent."""


@dataclass
class LlmCall:
    purpose: str
    seconds: float
    prompt_tokens: int
    completion_tokens: int
    served_model: str = ""


class LlmCallRecord(BaseModel):
    """One hosted-LLM call: the `llm_calls` columns of the run log, except `run_id` and `seq`,
    which the run logger assigns. `retry_of` is the index (in `attempts`) of the call this one
    retried; the logger maps it to `retry_of_seq`."""

    model_config = ConfigDict(extra="forbid")

    node: str | None = None
    purpose: str
    provider: str
    model: str
    model_version: str
    prompt_id: str
    prompt_version: int
    prompt_sha256: str
    temperature: float
    variables: dict[str, Any]
    rendered_prompt: str
    response_text: str
    parsed_ok: bool
    parse_error: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd_est: float | None
    retry_of: int | None = None
    earlier_attempts: list["LlmCallRecord"] = Field(default_factory=list)


class CallCounter(Protocol):
    """The run's counters (`Counters` in agents/state.py); only `llm_calls` is used here."""

    llm_calls: int


@dataclass
class ChatReply:
    content: str
    tokens_in: int
    tokens_out: int
    served_model: str
    latency_ms: int


Transport = Callable[[str, str, str, float, int | None], ChatReply]
"""(system, user, model, temperature, max_output_tokens) -> reply; raises `LlmError` on a
non-transient failure and `TransientError` on one worth retrying."""


class TransientError(LlmError):
    """A timeout, a network error or a retryable HTTP status."""


def _gcloud_token() -> str:
    try:
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        msg = "no Vertex AI token: run `gcloud auth application-default login`"
        raise LlmError(msg) from error
    return result.stdout.strip()


def vertex_base_url(project: str, location: str) -> str:
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else (f"{location}-aiplatform.googleapis.com")
    )
    return f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"


def http_transport(base_url: str, token: Callable[[], str], timeout_s: float = 60.0) -> Transport:
    """An OpenAI-compatible chat-completions transport with JSON output."""

    def send(
        system: str, user: str, model: str, temperature: float, max_tokens: int | None
    ) -> ChatReply:
        body = {
            "model": model,
            "temperature": temperature,
            **({"max_tokens": max_tokens} if max_tokens else {}),
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {token()}", "User-Agent": USER_AGENT},
                json=body,
                timeout=timeout_s,
            )
        except httpx.HTTPError as error:
            raise TransientError(type(error).__name__) from error
        if response.status_code in TRANSIENT_STATUS:
            raise TransientError(f"HTTP {response.status_code}")
        if response.status_code != 200:
            raise LlmError(f"HTTP {response.status_code}: {response.text[:300]}")
        payload = response.json()
        usage = payload.get("usage") or {}
        return ChatReply(
            content=payload["choices"][0]["message"]["content"] or "",
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
            served_model=str(payload.get("model", model)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    return send


@dataclass
class LlmClient:
    api_key: str
    model: str
    base_url: str = GEMINI_OPENAI_BASE
    timeout_s: float = 60.0
    provider: str = "ai_studio"
    temperature: float = 0.0
    max_llm_calls: int = 8
    price_per_mtok: dict[str, float | None] = field(default_factory=dict)
    max_output_tokens: dict[str, int] = field(default_factory=dict)  # per purpose
    registry: PromptRegistry | None = None
    transport: Transport | None = None
    backoff_s: float = 1.0

    @classmethod
    def from_env(cls) -> "LlmClient":
        key, model = os.environ.get("LLM_API_KEY"), os.environ.get("LLM_MODEL")
        if not key or not model:
            msg = "set LLM_API_KEY and LLM_MODEL (and LLM_BASE_URL if not Gemini) in .env"
            raise LlmError(msg)
        return cls(key, model, os.environ.get("LLM_BASE_URL") or GEMINI_OPENAI_BASE)

    @classmethod
    def from_config(
        cls, tier: str | None = None, max_llm_calls: int = 8, path: Path = MODEL_CONFIG
    ) -> "LlmClient":
        """Build the agent's client from `configs/model.yaml` and the environment."""
        config = yaml.safe_load(path.read_text(encoding="utf-8"))["hosted_llm"]
        tier = tier or config["default_tier"]
        model = os.environ.get("LLM_MODEL") or config["tiers"][tier]
        prices = config.get("price_per_mtok", {}).get(tier, {}) or {}
        common = {
            "provider": config["provider"],
            "temperature": float(config.get("temperature", 0)),
            "max_llm_calls": max_llm_calls,
            "price_per_mtok": {k: prices.get(k) for k in ("input", "output")},
            "max_output_tokens": dict(config.get("max_output_tokens") or {}),
        }
        if config["provider"] == "vertex":
            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = config.get("location") or os.environ.get("GOOGLE_CLOUD_LOCATION")
            if not project or not location:
                msg = "set GOOGLE_CLOUD_PROJECT and hosted_llm.location for Vertex AI"
                raise LlmError(msg)
            model_id = model if model.startswith("google/") else f"google/{model}"
            base = vertex_base_url(project, location)
            return cls("", model_id, base, transport=http_transport(base, _gcloud_token), **common)
        key = os.environ.get("LLM_API_KEY")
        if not key:
            raise LlmError("set LLM_API_KEY for the ai_studio provider")
        base = config.get("ai_studio_base_url") or GEMINI_OPENAI_BASE
        return cls(key, model, base, transport=http_transport(base, lambda: key), **common)

    # ------------------------------------------------------------------ v0 / proof of concept

    def json_call(self, purpose: str, system: str, user: str) -> tuple[dict[str, Any], LlmCall]:
        """One chat call that must return a JSON object. Retries once on transient errors."""
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        start = time.perf_counter()
        for attempt in range(3):
            try:
                response = httpx.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "india-analyst-agent/0.0",
                    },
                    json=body,
                    timeout=self.timeout_s,
                )
            except httpx.HTTPError as error:
                if attempt == 2:
                    raise LlmError(f"{purpose}: {type(error).__name__}") from error
                time.sleep(2 * (attempt + 1))
                continue
            if response.status_code in {429, 500, 503} and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            if response.status_code != 200:
                raise LlmError(f"{purpose}: HTTP {response.status_code}: {response.text[:300]}")
            break
        payload = response.json()
        content = payload["choices"][0]["message"]["content"] or ""
        usage = payload.get("usage") or {}
        call = LlmCall(
            purpose,
            round(time.perf_counter() - start, 3),
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
            str(payload.get("model", "")),
        )
        return parse_json(content, purpose), call

    # ------------------------------------------------------------------ agent calls

    def _transport(self) -> Transport:
        if self.transport is None:
            key = self.api_key
            self.transport = http_transport(self.base_url, lambda: key, self.timeout_s)
        return self.transport

    def _cost(self, tokens_in: int, tokens_out: int) -> float | None:
        price_in, price_out = self.price_per_mtok.get("input"), self.price_per_mtok.get("output")
        if price_in is None or price_out is None:
            return None
        return (tokens_in * price_in + tokens_out * price_out) / 1_000_000

    def structured(
        self,
        purpose: str,
        prompt_id: str,
        variables: dict[str, Any],
        schema: type[SchemaT],
        *,
        counters: CallCounter,
        validate: Callable[[SchemaT], None] | None = None,
        node: str | None = None,
        max_attempts: int = 2,
    ) -> tuple[SchemaT, LlmCallRecord]:
        """Render, call, parse and validate; one retry. `validate` raises `ValueError` for a
        reply that parses but breaks a rule (for example an id that was not retrieved); that
        counts as a parse failure and is retried with the same prompt.

        `counters.llm_calls` is incremented before each call, and a call is refused with
        `BudgetExhaustedError` when it would exceed `max_llm_calls`. On final failure,
        `LlmError.records` holds every attempt, for the run log."""
        registry = self.registry or PromptRegistry()
        prompt: Prompt = registry.get(prompt_id)
        rendered = prompt.render(variables)
        attempts: list[LlmCallRecord] = []
        for attempt in range(max_attempts):
            if counters.llm_calls >= self.max_llm_calls:
                raise BudgetExhaustedError(f"{purpose}: LLM-call budget spent", attempts)
            counters.llm_calls += 1
            record, fatal = self._attempt(
                prompt, rendered.system, rendered.user, purpose, variables, node
            )
            record.retry_of = attempt - 1 if attempt else None
            if fatal:  # a non-transient provider error is not worth a second call
                raise LlmError(f"{purpose}: {record.parse_error}", [*attempts, record])
            if record.parsed_ok:
                try:
                    parsed = schema.model_validate(parse_json(record.response_text, purpose))
                    if validate is not None:
                        validate(parsed)
                except (LlmError, ValidationError, ValueError) as error:
                    record.parsed_ok = False
                    record.parse_error = _short(error)
                else:
                    record.earlier_attempts = attempts
                    return parsed, record
            attempts.append(record)
            if attempt + 1 < max_attempts:
                time.sleep(self.backoff_s * (2**attempt))
        raise LlmError(f"{purpose}: no valid reply after {max_attempts} attempts", attempts)

    def _attempt(
        self,
        prompt: Prompt,
        system: str,
        user: str,
        purpose: str,
        variables: dict[str, Any],
        node: str | None,
    ) -> tuple[LlmCallRecord, bool]:
        """One call; returns the record and whether the failure (if any) is non-transient."""
        base = {
            "node": node,
            "purpose": purpose,
            "provider": self.provider,
            "model": self.model,
            "prompt_id": prompt.id,
            "prompt_version": prompt.version,
            "prompt_sha256": prompt.sha256,
            "temperature": self.temperature,
            "variables": json.loads(json.dumps(variables, default=str)),
            "rendered_prompt": f"## System\n{system}\n## User\n{user}",
        }
        try:
            reply = self._transport()(
                system, user, self.model, self.temperature, self.max_output_tokens.get(purpose)
            )
        except LlmError as error:  # recorded; retried only when transient
            failed = LlmCallRecord(
                **base,
                model_version="",
                response_text="",
                parsed_ok=False,
                parse_error=f"transport: {_short(error)}",
                tokens_in=0,
                tokens_out=0,
                latency_ms=0,
                cost_usd_est=None,
            )
            return failed, not isinstance(error, TransientError)
        return LlmCallRecord(
            **base,
            model_version=reply.served_model,
            response_text=reply.content,
            parsed_ok=True,
            parse_error=None,
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            latency_ms=reply.latency_ms,
            cost_usd_est=self._cost(reply.tokens_in, reply.tokens_out),
        ), False


def _short(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error)[:300]}"


def parse_json(content: str, purpose: str = "reply") -> dict[str, Any]:
    """The JSON object in a reply, with or without a code fence."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL)
    text = fenced.group(1) if fenced else content
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise LlmError(f"{purpose}: reply is not JSON: {content[:200]}") from error
    if not isinstance(value, dict):
        raise LlmError(f"{purpose}: reply is not a JSON object")
    return value
