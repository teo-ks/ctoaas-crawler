"""LLM client abstraction — Anthropic direct or OpenAI-compatible (LiteLLM, etc.)."""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Models and pricing
# ---------------------------------------------------------------------------

DEFAULT_MODEL: str = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")
FALLBACK_MODEL: str = os.getenv("LLM_FALLBACK_MODEL", "claude-sonnet-4-6")

# Per-1M-token pricing (input / output)
PRICING_PER_1M: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001":  {"input": 0.80,  "output": 4.00},
    "claude-haiku-4-5":           {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":          {"input": 3.00,  "output": 15.00},
    "claude-opus-4-6":            {"input": 15.00, "output": 75.00},
    # AWS Bedrock (via LiteLLM)
    "bedrock-claude-haiku-3":     {"input": 0.25,  "output": 1.25},
    "bedrock-claude-haiku-3-5":   {"input": 0.80,  "output": 4.00},
    "bedrock-claude-sonnet-4":    {"input": 3.00,  "output": 15.00},
    "bedrock-claude-sonnet-4-5":  {"input": 3.00,  "output": 15.00},
    # Google (via LiteLLM)
    "google-gemini-3-flash":      {"input": 0.15,  "output": 0.60},
    "gemini/gemini-2.0-flash":    {"input": 0.15,  "output": 0.60},
    # OpenRouter model IDs
    "google/gemini-2.0-flash-001":     {"input": 0.10,  "output": 0.40},
    "google/gemini-flash-1.5":         {"input": 0.075, "output": 0.30},
    "anthropic/claude-haiku-4.5":      {"input": 0.80,  "output": 4.00},
    "anthropic/claude-haiku-4-5":      {"input": 0.80,  "output": 4.00},
    "anthropic/claude-3-haiku":        {"input": 0.25,  "output": 1.25},
    "anthropic/claude-3.5-haiku":      {"input": 0.80,  "output": 4.00},
    "anthropic/claude-sonnet-4-5":     {"input": 3.00,  "output": 15.00},
}


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    content: str
    usage: LLMUsage


def estimate_cost(usage: LLMUsage, model: str) -> float | None:
    pricing = PRICING_PER_1M.get(model)
    if not pricing:
        return None
    return (usage.input_tokens / 1_000_000) * pricing["input"] + (
        usage.output_tokens / 1_000_000
    ) * pricing["output"]


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class CostTracker:
    def __init__(self) -> None:
        self._total_input = 0
        self._total_output = 0
        self._call_count = 0

    def record(self, usage: LLMUsage, model: str, label: str) -> None:
        self._total_input += usage.input_tokens
        self._total_output += usage.output_tokens
        self._call_count += 1

        cost = estimate_cost(usage, model)
        cost_str = f"${cost:.4f}" if cost is not None else "unknown pricing"
        print(
            f"[tokens] {label} | in:{usage.input_tokens:,} out:{usage.output_tokens:,}"
            f" | {cost_str} | model:{model}"
        )

    def summary(self) -> None:
        model = os.getenv("LLM_MODEL", "")
        pricing = PRICING_PER_1M.get(model)
        total_cost = None
        if pricing:
            total_cost = (
                (self._total_input / 1_000_000) * pricing["input"]
                + (self._total_output / 1_000_000) * pricing["output"]
            )
        cost_str = f"${total_cost:.4f}" if total_cost is not None else "unknown pricing"
        sys.stderr.write(
            f"\n[tokens] TOTAL | {self._call_count} calls"
            f" | in:{self._total_input:,} out:{self._total_output:,}"
            f" | est. {cost_str} | model:{model}\n"
        )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, messages: list[LLMMessage], model: str) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Anthropic SDK client
# ---------------------------------------------------------------------------


class AnthropicClient(LLMClient):
    def __init__(self) -> None:
        import anthropic  # type: ignore
        import httpx

        # trust_env=False ensures no HTTP_PROXY/HTTPS_PROXY env vars affect LLM calls
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            http_client=httpx.AsyncClient(trust_env=False),
        )

    async def complete(self, messages: list[LLMMessage], model: str) -> LLMResponse:
        import anthropic  # type: ignore

        response = await self._client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        block = response.content[0]
        if block.type != "text":
            raise ValueError("Unexpected non-text response from Anthropic")
        return LLMResponse(
            content=block.text,
            usage=LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible client (LiteLLM, OpenRouter, etc.)
# ---------------------------------------------------------------------------


class OpenAICompatibleClient(LLMClient):
    def __init__(self, base_url: str) -> None:
        from openai import AsyncOpenAI  # type: ignore
        import httpx

        api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "dummy"
        # trust_env=False ensures no HTTP_PROXY/HTTPS_PROXY env vars affect LLM calls
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.AsyncClient(trust_env=False),
        )

    async def complete(self, messages: list[LLMMessage], model: str) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],  # type: ignore
            max_tokens=4096,
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            content=content,
            usage=LLMUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_llm_client() -> LLMClient:
    raw_base_url = os.getenv("LLM_BASE_URL")
    if raw_base_url:
        import re

        # Only strip if the user pasted the full endpoint path — keep /v1 intact
        # so the OpenAI SDK can append /chat/completions correctly.
        base_url = re.sub(r"/chat/completions/?$", "", raw_base_url)
        base_url = re.sub(r"/completions/?$", "", base_url)
        print(f"[llm] Using OpenAI-compatible client → {base_url}")
        return OpenAICompatibleClient(base_url)
    print("[llm] Using Anthropic client (direct)")
    return AnthropicClient()
