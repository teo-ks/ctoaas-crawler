"""Abstract base class for extraction agents."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from ..llm.client import CostTracker, LLMClient, LLMMessage, DEFAULT_MODEL, FALLBACK_MODEL
from ..utils.html_cleaner import clean_html, estimate_tokens

MAX_TOKEN_BUDGET = 60_000  # ~60k tokens is the safe ceiling before costs spike


class BaseExtractionAgent(ABC):
    def __init__(self, llm_client: LLMClient, cost_tracker: CostTracker | None = None) -> None:
        self._llm = llm_client
        self._cost_tracker = cost_tracker

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def parse_response(self, raw: str, url: str) -> list[Any]: ...

    @abstractmethod
    def filter_quality(self, items: list[Any]) -> list[Any]: ...

    # ------------------------------------------------------------------
    # Shared extraction logic (lives once here)
    # ------------------------------------------------------------------

    async def extract(self, raw_html: str, url: str) -> list[Any]:
        cleaned = clean_html(raw_html)

        content = cleaned
        tokens = estimate_tokens(cleaned)
        if tokens > MAX_TOKEN_BUDGET:
            print(
                f"[extraction] HTML ~{tokens} est. tokens — truncating to budget for {url}"
            )
            content = cleaned[: MAX_TOKEN_BUDGET * 4]

        messages = [
            LLMMessage(
                role="user",
                content=f"{self.system_prompt}\n\nSource URL: {url}\n\nHTML:\n{content}",
            )
        ]

        raw_response: str
        try:
            response = await self._llm.complete(messages, DEFAULT_MODEL)
            raw_response = response.content
            if self._cost_tracker:
                self._cost_tracker.record(response.usage, DEFAULT_MODEL, url)
        except Exception as e:
            print(f"[extraction] Primary model failed for {url} — trying fallback: {e}")
            try:
                response = await self._llm.complete(messages, FALLBACK_MODEL)
                raw_response = response.content
                if self._cost_tracker:
                    self._cost_tracker.record(response.usage, FALLBACK_MODEL, f"{url} (fallback)")
            except Exception as e2:
                print(f"[extraction] Fallback model also failed for {url} — skipping: {e2}")
                return []

        items = self.parse_response(raw_response, url)
        return self.filter_quality(items)

    # ------------------------------------------------------------------
    # Shared JSON parse helper
    # ------------------------------------------------------------------

    @staticmethod
    def strip_fences(raw: str) -> str:
        """Remove markdown code fences the LLM may have added despite instructions."""
        return re.sub(r"```(?:json)?\n?", "", raw).strip()
