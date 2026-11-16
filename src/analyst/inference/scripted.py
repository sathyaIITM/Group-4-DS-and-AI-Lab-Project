"""Scripted hosted-LLM transport: offline runs and tests of the nodes that call the LLM.

Replies are returned in order, so a test or a dry run of the graph needs no network and no key.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from analyst.inference.llm import ChatReply, LlmClient, LlmError


@dataclass
class ScriptedTransport:
    """Replies in order; a reply is a dict (sent as JSON), a str (sent as is) or an exception."""

    replies: list[Any]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, system: str, user: str, model: str, temperature: float) -> ChatReply:
        self.calls.append((system, user))
        if not self.replies:
            raise LlmError("script exhausted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return ChatReply(content, tokens_in=100, tokens_out=20, served_model=model, latency_ms=5)


@dataclass
class Counters:
    llm_calls: int = 0


def scripted_client(*replies: Any, max_llm_calls: int = 8) -> tuple[LlmClient, ScriptedTransport]:
    transport = ScriptedTransport(list(replies))
    client = LlmClient(
        "",
        "gemini-test",
        transport=transport,
        max_llm_calls=max_llm_calls,
        backoff_s=0.0,
        price_per_mtok={"input": 0.1, "output": 0.4},
    )
    return client, transport
