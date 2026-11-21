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
import shutil
import signal
import subprocess
import threading
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
    """Timing and token counts of one model call."""

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
    # Additions to the Section 9 columns (thinking control): the level sent, the thinking tokens
    # reported (billed as output) and why generation stopped ("length" means cut at the cap).
    thinking_level: str | None = None
    reasoning_tokens: int | None = None
    finish_reason: str | None = None
    cached_tokens: int | None = None  # part of tokens_in served from the implicit cache
    retry_of: int | None = None
    earlier_attempts: list["LlmCallRecord"] = Field(default_factory=list)


class CallCounter(Protocol):
    """The run's counters (`Counters` in agents/state.py); only `llm_calls` is used here."""

    llm_calls: int


THINKING_ORDER = ("minimal", "low", "medium", "high")


@dataclass
class ChatRequest:
    """A chat completion request: prompts, model, temperature, token cap and schema."""

    system: str
    user: str
    model: str
    temperature: float
    max_tokens: int | None = None
    reasoning_effort: str | None = None  # maps to thinking_level on Gemini 3 models
    response_schema: dict[str, Any] | None = None  # JSON Schema the reply must follow


@dataclass
class ChatReply:
    """A chat completion reply with its token counts and latency."""

    content: str
    tokens_in: int
    tokens_out: int
    served_model: str
    latency_ms: int
    reasoning_tokens: int | None = None  # when the provider reports them separately
    finish_reason: str | None = None
    cached_tokens: int | None = None  # input tokens served from the provider's implicit cache


Transport = Callable[[ChatRequest], ChatReply]
"""Request -> reply; raises `LlmError` on a non-transient failure and `TransientError` on one
worth retrying."""


def request_body(request: ChatRequest) -> dict[str, Any]:
    """The OpenAI-compatible body. Thinking is set only through `reasoning_effort`, never also
    through `thinking_config` or the deprecated `thinking_budget`."""
    body: dict[str, Any] = {
        "model": request.model,
        "temperature": request.temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ],
    }
    if request.max_tokens:
        body["max_tokens"] = request.max_tokens
    if request.reasoning_effort:
        body["reasoning_effort"] = request.reasoning_effort
    if request.response_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "reply", "schema": request.response_schema},
        }
    return body


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A Pydantic JSON Schema with every `$ref` replaced by its definition and `$defs` and
    `title` removed, the self-contained form providers accept most widely."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        """Replace schema references with their definitions."""
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in {"$defs", "title"}}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    result: dict[str, Any] = walk(schema)
    return result


def coerce_lists(data: dict[str, Any], schema: type[BaseModel]) -> dict[str, Any]:
    """Repair the two shape slips models make in list fields before validation: `null` becomes
    `[]`, and a single object becomes a one-item list. Nothing else is changed."""
    fixed = dict(data)
    for name, info in schema.model_fields.items():
        origin = getattr(info.annotation, "__origin__", None)
        if origin is not list or name not in fixed:
            continue
        if fixed[name] is None:
            fixed[name] = []
        elif isinstance(fixed[name], dict):
            fixed[name] = [fixed[name]]
    return fixed


def billed_output_tokens(reply: ChatReply) -> int:
    """Output tokens as billed: the visible reply plus the thinking tokens, which Vertex reports
    separately from `completion_tokens` (checked 2026-11-17 with gemini-3.5-flash-lite)."""
    return reply.tokens_out + (reply.reasoning_tokens or 0)


def parse_reply(payload: dict[str, Any], model: str, latency_ms: int) -> ChatReply:
    """Read a chat completion response into a reply."""
    usage = payload.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    choice = payload["choices"][0]
    reasoning = details.get("reasoning_tokens")
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    return ChatReply(
        content=choice["message"].get("content") or "",
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=int(usage.get("completion_tokens", 0)),
        served_model=str(payload.get("model", model)),
        latency_ms=latency_ms,
        reasoning_tokens=int(reasoning) if reasoning is not None else None,
        finish_reason=choice.get("finish_reason"),
        cached_tokens=int(cached) if cached is not None else None,
    )


CACHED_INPUT_SHARE = 0.1  # cached input billed at 10% of the input price


class TransientError(LlmError):
    """A timeout, a network error or a retryable HTTP status."""


class RateLimitedError(TransientError):
    """HTTP 429: retried after a longer pause (test ladder, 19 Nov: up to 82 per run)."""


RATE_LIMIT_PAUSE_S = 8.0  # first pause after a 429; doubled on the next attempt


def clear_token() -> None:
    """Forget the cached access token, so the next call fetches a new one."""
    with _TOKEN_LOCK:
        _TOKEN["value"] = None


_TOKEN: dict[str, Any] = {"value": None, "at": 0.0}
_TOKEN_LOCK = threading.Lock()
TOKEN_TTL_S = 45 * 60  # access tokens last about an hour
TOKEN_TIMEOUT_S = 20


def _fetch_gcloud_token() -> str:
    """Run gcloud in its own process group, so a hung child cannot hold the pipes open.

    The executable is resolved on PATH first: on Windows gcloud is `gcloud.cmd`, which a bare
    `gcloud` argument does not find.
    """
    executable = shutil.which("gcloud")
    if executable is None:
        msg = "gcloud not found on PATH: install the Google Cloud CLI"
        raise LlmError(msg)
    process = subprocess.Popen(  # noqa: S603  # fixed arguments; executable resolved on PATH
        [executable, "auth", "application-default", "print-access-token"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # ignored on Windows
    )
    try:
        out, _ = process.communicate(timeout=TOKEN_TIMEOUT_S)
    except subprocess.TimeoutExpired as error:
        if hasattr(os, "killpg"):
            os.killpg(process.pid, signal.SIGKILL)
        else:  # Windows: no process groups in the POSIX sense
            process.kill()
        process.communicate()
        msg = f"gcloud did not return a token within {TOKEN_TIMEOUT_S} s"
        raise LlmError(msg) from error
    if process.returncode != 0 or not out.strip():
        msg = "no Vertex AI token: run `gcloud auth application-default login`"
        raise LlmError(msg)
    return out.strip()


def gcloud_token() -> str:
    """An application-default access token, cached for 45 minutes (one gcloud run per hour,
    not one per call); questions run in parallel threads, so the cache is locked."""
    with _TOKEN_LOCK:
        # Wall-clock time: the monotonic clock stops while a Mac sleeps, so a token cached
        # before a sleep was used after it had expired (test ladder, 19 Nov: 401 on every call).
        now = time.time()
        if _TOKEN["value"] is None or now - float(_TOKEN["at"]) > TOKEN_TTL_S:
            try:
                _TOKEN["value"] = _fetch_gcloud_token()
            except OSError as error:
                msg = "no Vertex AI token: run `gcloud auth application-default login`"
                raise LlmError(msg) from error
            _TOKEN["at"] = now
        return str(_TOKEN["value"])


def vertex_base_url(project: str, location: str) -> str:
    """Return the OpenAI-compatible Vertex AI base URL for a project and location."""
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else (f"{location}-aiplatform.googleapis.com")
    )
    return f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"


def http_transport(base_url: str, token: Callable[[], str], timeout_s: float = 60.0) -> Transport:
    """An OpenAI-compatible chat-completions transport with JSON output."""

    def send(request: ChatRequest) -> ChatReply:
        """Send a request, refreshing the token once on an authentication error."""
        body = request_body(request)
        started = time.perf_counter()
        for refreshed in (False, True):
            try:
                response = httpx.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {token()}", "User-Agent": USER_AGENT},
                    json=body,
                    timeout=timeout_s,
                )
            except httpx.HTTPError as error:
                raise TransientError(type(error).__name__) from error
            if response.status_code in {401, 403} and not refreshed:
                clear_token()  # an expired or revoked token: fetch a new one and retry once
                continue
            break
        if response.status_code == 429:
            raise RateLimitedError("HTTP 429")
        if response.status_code in TRANSIENT_STATUS:
            raise TransientError(f"HTTP {response.status_code}")
        if response.status_code != 200:
            raise LlmError(f"HTTP {response.status_code}: {response.text[:300]}")
        latency = int((time.perf_counter() - started) * 1000)
        return parse_reply(response.json(), request.model, latency)

    return send


@dataclass
class LlmClient:
    """Client for structured model calls with retries, budgets and call records."""

    api_key: str
    model: str
    base_url: str = GEMINI_OPENAI_BASE
    timeout_s: float = 60.0
    provider: str = "ai_studio"
    temperature: float = 0.0
    max_llm_calls: int = 8
    price_per_mtok: dict[str, float | None] = field(default_factory=dict)
    max_output_tokens: dict[str, int] = field(default_factory=dict)  # per purpose
    schema_output: bool = False  # send the reply's JSON Schema (response_format json_schema)
    thinking: dict[str, str] = field(default_factory=dict)  # reasoning_effort per purpose
    thinking_on_regenerate: dict[str, str] = field(default_factory=dict)
    thinking_allowance: dict[str, int] = field(default_factory=dict)  # extra cap per level
    supported_levels: dict[str, list[str]] = field(default_factory=dict)  # per model id
    registry: PromptRegistry | None = None
    transport: Transport | None = None
    backoff_s: float = 1.0

    @classmethod
    def from_env(cls) -> "LlmClient":
        """Build a client from the LLM_* environment variables."""
        key, model = os.environ.get("LLM_API_KEY"), os.environ.get("LLM_MODEL")
        if not key or not model:
            msg = "set LLM_API_KEY and LLM_MODEL (and LLM_BASE_URL if not Gemini) in .env"
            raise LlmError(msg)
        return cls(key, model, os.environ.get("LLM_BASE_URL") or GEMINI_OPENAI_BASE)

    @classmethod
    def from_config(
        cls, tier: str | None = None, max_llm_calls: int = 8, path: Path = MODEL_CONFIG
    ) -> "LlmClient":
        """Build the agent's client from `configs/model.yaml` and the environment.

        The model comes only from `model.yaml` (the tier's id); `LLM_MODEL` is not read here, so
        an old `.env` entry cannot switch the agent to another model unnoticed. To use another
        model, change `model.yaml` or pass `tier`. The environment supplies only credentials
        and the project (`LLM_API_KEY`, `GOOGLE_CLOUD_PROJECT`)."""
        config = yaml.safe_load(path.read_text(encoding="utf-8"))["hosted_llm"]
        tier = tier or config["default_tier"]
        model = config["tiers"][tier]
        prices = config.get("price_per_mtok", {}).get(tier, {}) or {}
        thinking = config.get("thinking") or {}
        timeout_s = float(config.get("request_timeout_s", 60))
        common = {
            "provider": config["provider"],
            "temperature": float(config.get("temperature", 0)),
            "max_llm_calls": max_llm_calls,
            "timeout_s": timeout_s,
            "price_per_mtok": {k: prices.get(k) for k in ("input", "output")},
            "max_output_tokens": dict(config.get("max_output_tokens") or {}),
            "schema_output": config.get("response_format") == "json_schema",
            "thinking": dict(thinking.get("per_purpose") or {}),
            "thinking_on_regenerate": dict(thinking.get("on_regenerate") or {}),
            "thinking_allowance": {k: int(v) for k, v in (thinking.get("allowance") or {}).items()},
            "supported_levels": {
                k: list(v) for k, v in (thinking.get("supported_levels") or {}).items()
            },
        }
        if config["provider"] == "vertex":
            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            location = config.get("location") or os.environ.get("GOOGLE_CLOUD_LOCATION")
            if not project or not location:
                msg = "set GOOGLE_CLOUD_PROJECT and hosted_llm.location for Vertex AI"
                raise LlmError(msg)
            model_id = model if model.startswith("google/") else f"google/{model}"
            base = vertex_base_url(project, location)
            transport = http_transport(base, gcloud_token, timeout_s)
            return cls("", model_id, base, transport=transport, **common)
        key = os.environ.get("LLM_API_KEY")
        if not key:
            raise LlmError("set LLM_API_KEY for the ai_studio provider")
        base = config.get("ai_studio_base_url") or GEMINI_OPENAI_BASE
        return cls(
            key, model, base, transport=http_transport(base, lambda: key, timeout_s), **common
        )

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
        """Return the transport, creating the HTTP transport on first use."""
        if self.transport is None:
            key = self.api_key
            self.transport = http_transport(self.base_url, lambda: key, self.timeout_s)
        return self.transport

    def thinking_level(self, purpose: str, regenerate: bool = False) -> str | None:
        """The `reasoning_effort` for a call: the purpose's level (or its regeneration level),
        moved up to the nearest level the model accepts. None sends no setting (model default)."""
        wanted = (regenerate and self.thinking_on_regenerate.get(purpose)) or self.thinking.get(
            purpose
        )
        if not wanted:
            return None
        if wanted not in THINKING_ORDER:
            raise LlmError(f"unknown thinking level {wanted!r} for {purpose}")
        accepted = self.supported_levels.get(self.model.removeprefix("google/"))
        if not accepted:
            return wanted
        for level in THINKING_ORDER[THINKING_ORDER.index(wanted) :]:
            if level in accepted:
                return level
        raise LlmError(f"{self.model} accepts none of the levels at or above {wanted!r}")

    def output_cap(self, purpose: str, effort: str | None) -> int | None:
        """The purpose's cap for the visible reply plus the thinking allowance of the level;
        thinking tokens count against the cap. None when the purpose has no cap."""
        base = self.max_output_tokens.get(purpose)
        if base is None:
            return None
        return base + (self.thinking_allowance.get(effort, 0) if effort else 0)

    def _cost(self, tokens_in: int, tokens_out: int, cached: int = 0) -> float | None:
        """Estimate in USD; cached input tokens are billed at 10% of the input price (Vertex AI
        implicit caching gives 90% off cached tokens; checked in the documentation 18 Nov)."""
        price_in, price_out = self.price_per_mtok.get("input"), self.price_per_mtok.get("output")
        if price_in is None or price_out is None:
            return None
        cached = min(max(cached, 0), tokens_in)
        billed_in = (tokens_in - cached) + cached * CACHED_INPUT_SHARE
        return (billed_in * price_in + tokens_out * price_out) / 1_000_000

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
        regenerate: bool = False,
    ) -> tuple[SchemaT, LlmCallRecord]:
        """Render, call, parse and validate; one retry. `validate` raises `ValueError` for a
        reply that parses but breaks a rule (for example an id that was not retrieved); that
        counts as a parse failure and is retried with the same prompt.

        `counters.llm_calls` is incremented before each call, and a call is refused with
        `BudgetExhaustedError` when it would exceed `max_llm_calls`. On final failure,
        `LlmError.records` holds every attempt, for the run log.

        The thinking level comes from `configs/model.yaml` for the purpose; `regenerate=True`
        uses the purpose's regeneration level (a query regenerated after a failed check)."""
        registry = self.registry or PromptRegistry()
        prompt: Prompt = registry.get(prompt_id)
        rendered = prompt.render(variables)
        effort = self.thinking_level(purpose, regenerate)
        attempts: list[LlmCallRecord] = []
        for attempt in range(max_attempts):
            if counters.llm_calls >= self.max_llm_calls:
                raise BudgetExhaustedError(f"{purpose}: LLM-call budget spent", attempts)
            counters.llm_calls += 1
            record, fatal = self._attempt(
                prompt, rendered.system, rendered.user, purpose, variables, node, effort, schema
            )
            record.retry_of = attempt - 1 if attempt else None
            if fatal:  # a non-transient provider error is not worth a second call
                raise LlmError(f"{purpose}: {record.parse_error}", [*attempts, record])
            if record.parsed_ok:
                try:
                    raw = coerce_lists(parse_json(record.response_text, purpose), schema)
                    parsed = schema.model_validate(raw)
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
                limited = "HTTP 429" in (record.parse_error or "")
                pause = RATE_LIMIT_PAUSE_S if limited and self.backoff_s > 0 else self.backoff_s
                time.sleep(pause * (2**attempt))
        raise LlmError(f"{purpose}: no valid reply after {max_attempts} attempts", attempts)

    def _attempt(
        self,
        prompt: Prompt,
        system: str,
        user: str,
        purpose: str,
        variables: dict[str, Any],
        node: str | None,
        effort: str | None = None,
        schema: type[BaseModel] | None = None,
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
            "thinking_level": effort,
        }
        try:
            reply = self._transport()(
                ChatRequest(
                    system,
                    user,
                    self.model,
                    self.temperature,
                    self.output_cap(purpose, effort),
                    effort,
                    inline_schema(schema.model_json_schema())
                    if self.schema_output and schema is not None
                    else None,
                )
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
            cost_usd_est=self._cost(
                reply.tokens_in, billed_output_tokens(reply), reply.cached_tokens or 0
            ),
            reasoning_tokens=reply.reasoning_tokens,
            finish_reason=reply.finish_reason,
            cached_tokens=reply.cached_tokens,
        ), False


def _short(error: Exception) -> str:
    """Return a short description of an error."""
    return f"{type(error).__name__}: {str(error)[:300]}"


def salvage_json(text: str) -> dict[str, Any] | None:
    """The usable part of a reply that is not valid JSON as a whole: the first complete object
    (a reply followed by runaway text or newlines), or the object cut after its last complete
    top-level field (a reply whose last field ran on until the output cap). Smoke run, 19 Nov:
    16 intent replies looped inside a free-text field until cut. The schema check still applies,
    so a reply that lacks a required field is still rejected."""
    start = text.find("{")
    if start < 0:
        return None
    body = text[start:]
    try:
        value, _ = json.JSONDecoder().raw_decode(body)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    cuts: list[int] = []  # positions of commas between top-level members
    depth, in_string, escaped = 0, False, False
    for i, char in enumerate(body):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        elif char == "," and depth == 1:
            cuts.append(i)
    for cut in reversed(cuts):
        try:
            value = json.loads(body[:cut] + "}")
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else None
    return None


def parse_json(content: str, purpose: str = "reply") -> dict[str, Any]:
    """The JSON object in a reply, with or without a code fence."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL)
    text = fenced.group(1) if fenced else content
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        value = salvage_json(text)
        if value is None:
            raise LlmError(f"{purpose}: reply is not JSON: {content[:200]}") from error
    if not isinstance(value, dict):
        raise LlmError(f"{purpose}: reply is not a JSON object")
    return value
