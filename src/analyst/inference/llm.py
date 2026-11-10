"""Hosted LLM client over an OpenAI-compatible chat-completions endpoint.

Configured by environment: LLM_API_KEY, LLM_MODEL and LLM_BASE_URL. For Gemini through Google
AI Studio the base URL is https://generativelanguage.googleapis.com/v1beta/openai. Every call
returns its parsed JSON, token counts and latency, so the pipeline can report LLM calls and
tokens per answer.
"""

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


class LlmError(RuntimeError):
    """The model could not be reached or did not return valid JSON."""


@dataclass
class LlmCall:
    purpose: str
    seconds: float
    prompt_tokens: int
    completion_tokens: int


@dataclass
class LlmClient:
    api_key: str
    model: str
    base_url: str = GEMINI_OPENAI_BASE
    timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> "LlmClient":
        key, model = os.environ.get("LLM_API_KEY"), os.environ.get("LLM_MODEL")
        if not key or not model:
            msg = "set LLM_API_KEY and LLM_MODEL (and LLM_BASE_URL if not Gemini) in .env"
            raise LlmError(msg)
        return cls(key, model, os.environ.get("LLM_BASE_URL") or GEMINI_OPENAI_BASE)

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
        )
        return parse_json(content, purpose), call


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
