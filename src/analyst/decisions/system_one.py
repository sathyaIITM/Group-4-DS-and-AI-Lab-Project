"""Client for the System One decision API (TypeSafe Jev and a local Kev server).

Both backends accept POST /v1/systemone with a state and named questions, so one
client serves either; only the base URL, key and model name differ.
"""

import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field


class NoulQuestion(BaseModel):
    """A yes/no question; the answer is the probability of yes."""

    type: Literal["noul"] = "noul"
    instructions: str
    criteria: dict[str, str] | None = None


class SystemOneRequest(BaseModel):
    state: str | dict[str, Any] | list[Any]
    model: str
    questions: dict[str, NoulQuestion]


class NoulAnswer(BaseModel):
    noul: float


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class SystemOneResponse(BaseModel):
    answers: dict[str, NoulAnswer]
    usage: Usage = Field(default_factory=Usage)


class TimedAnswer(BaseModel):
    """Per-question yes-probabilities plus the wall-clock latency of the call."""

    probabilities: dict[str, float]
    latency_s: float = Field(ge=0.0)
    input_tokens: int = 0


class SystemOneClient:
    """Thin synchronous client; one call answers every question in the request."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        headers = {"User-Agent": "india-analyst-agent/0.0"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._model = model
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout_s)

    def ask(self, state: str, questions: dict[str, NoulQuestion]) -> TimedAnswer:
        payload = SystemOneRequest(state=state, model=self._model, questions=questions)
        started = time.perf_counter()
        response = self._client.post("/v1/systemone", json=payload.model_dump(exclude_none=True))
        latency = time.perf_counter() - started
        response.raise_for_status()
        parsed = SystemOneResponse.model_validate(response.json())
        return TimedAnswer(
            probabilities={name: ans.noul for name, ans in parsed.answers.items()},
            latency_s=latency,
            input_tokens=parsed.usage.input_tokens,
        )

    def close(self) -> None:
        self._client.close()
