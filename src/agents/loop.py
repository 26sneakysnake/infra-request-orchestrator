"""Tool-use loop shared by the agents: one model, read-only tools, a JSON schema for the answer."""

import json
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic

from agents.llm import anthropic_client, cost_usd, llm_model

# Server-side fallback on refusal exists for these models (not for Haiku 5.5).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

# (tool name, tool input) -> text returned to the model
Execute = Callable[[str, dict[str, Any]], str]


class AgentError(RuntimeError):
    """The agent produced no usable answer (refusal, truncated answer, or endless loop)."""


@dataclass
class AgentRun:
    answer: dict[str, Any]
    model: str
    turns: int
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.model, self.usage)


def run_tool_loop(
    *,
    system: str,
    tools: list[dict[str, Any]],
    schema: dict[str, Any],
    first_message: str,
    execute: Execute,
    max_turns: int,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> AgentRun:
    client = client or anthropic_client()
    model = model or llm_model()
    effort = effort or os.environ.get("NETCO_LLM_EFFORT", "medium")
    extra: dict[str, Any] = {}
    if model in FALLBACK_MODELS:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    if tools:  # an agent without tools answers in a single request
        extra["tools"] = tools
    messages: list[dict[str, Any]] = [{"role": "user", "content": first_message}]
    usage: Counter[str] = Counter()
    for turn in range(1, max_turns + 1):
        response = client.beta.messages.create(
            model=model,
            max_tokens=8000,
            # Explicit breakpoint: tools + system prompt are cached once and shared by all requests;
            # the automatic one below caches the growing conversation within a request.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            cache_control={"type": "ephemeral"},
            messages=messages,
            **extra,
        )
        for name in ("input_tokens", "output_tokens"):
            usage[name] += getattr(response.usage, name) or 0
        for name in ("cache_creation_input_tokens", "cache_read_input_tokens"):
            usage[name] += getattr(response.usage, name, None) or 0

        if response.stop_reason == "refusal":
            raise AgentError(f"the model declined the request: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            raise AgentError("answer truncated (max_tokens)")
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": execute(block.name, dict(block.input or {})),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": results})
            continue
        answer_text = next(b.text for b in response.content if b.type == "text")
        return AgentRun(json.loads(answer_text), model, turn, dict(usage))
    raise AgentError(f"no answer after {max_turns} turns")
