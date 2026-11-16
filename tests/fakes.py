from __future__ import annotations
from collections import defaultdict, deque
from typing import Any

class FakeLLM:
    """Deterministic fake LLM; scripts are keyed by operation/purpose."""
    def __init__(self, responses: dict[str, list[Any]] | None = None) -> None:
        self.responses = {key: deque(values) for key, values in (responses or {}).items()}
        self.calls: list[tuple[str, Any]] = []
    def complete(self, purpose: str, payload: Any = None) -> Any:
        self.calls.append((purpose, payload))
        queue = self.responses.get(purpose)
        if not queue:
            raise AssertionError(f"no scripted response for LLM purpose: {purpose}")
        return queue.popleft()

class FakeDecisionClient:
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, Any]] = []
    def decide(self, purpose: str, payload: Any = None) -> Any:
        self.calls.append((purpose, payload))
        if purpose not in self.responses:
            raise AssertionError(f"no scripted decision for: {purpose}")
        return self.responses[purpose]

class FakeIndex:
    def __init__(self, hits: list[Any] | None = None) -> None:
        self.hits = hits or []
        self.calls: list[dict[str, Any]] = []
    def search(self, query: str, *, kind: str, k: int, **kwargs: Any) -> list[Any]:
        self.calls.append({"query": query, "kind": kind, "k": k, **kwargs})
        return self.hits[:k]

class FakeToolSet:
    """Purpose-keyed fake tool responses, with call history for node tests."""
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, Any]] = []
    def call(self, purpose: str, payload: Any = None) -> Any:
        self.calls.append((purpose, payload))
        if purpose not in self.responses:
            raise AssertionError(f"no scripted tool response for: {purpose}")
        value = self.responses[purpose]
        return value(payload) if callable(value) else value
