"""FAQ extraction agent."""

from __future__ import annotations

import json
import re

from .base_extraction_agent import BaseExtractionAgent
from ..schemas.faq import FaqPair

JUNK_ANSWER_PATTERNS = [
    re.compile(r"not directly addressed", re.IGNORECASE),
    re.compile(r"not mentioned in the (provided |given )?html", re.IGNORECASE),
    re.compile(r"^placeholder", re.IGNORECASE),
    re.compile(r"no (faq|information) (found|available)", re.IGNORECASE),
]

_SYSTEM_PROMPT = """You are a precise data extraction agent. Your only job is to extract FAQ question-and-answer pairs from HTML.

Rules:
- Only extract content that is explicitly present in the HTML — never infer or fabricate
- Each pair must have BOTH a distinct question AND a distinct answer — never copy the question as the answer
- If an answer spans multiple paragraphs, join them with newline characters
- If the FAQ items belong to a named section or category, include it in the "category" field
- Return ONLY valid JSON — no markdown fences, no explanation, nothing else

Output format:
{"pairs": [{"question": "...", "answer": "...", "category": "..."}]}

If no FAQ pairs are found, return exactly: {"pairs": []}"""


class FaqExtractionAgent(BaseExtractionAgent):
    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def parse_response(self, raw: str, url: str) -> list[FaqPair]:
        try:
            cleaned = self.strip_fences(raw)
            parsed = json.loads(cleaned)

            if not isinstance(parsed.get("pairs"), list):
                print(f"[extraction] Unexpected response shape for {url}")
                print(f"[extraction] Raw (500 chars): {raw[:500]}")
                return []

            results: list[FaqPair] = []
            for p in parsed["pairs"]:
                if not isinstance(p.get("question"), str) or not isinstance(p.get("answer"), str):
                    continue
                results.append(
                    FaqPair(
                        question=p["question"].strip(),
                        answer=p["answer"].strip(),
                        category=p.get("category", "").strip() or None,
                    )
                )
            if not results:
                print(f"[extraction] Model returned 0 pairs for {url} | raw: {raw[:300]}")
            return results
        except Exception as e:
            print(f"[extraction] Failed to parse LLM response for {url}: {e}")
            print(f"[extraction] Raw response (first 500 chars): {raw[:500]}")
            return []

    def filter_quality(self, items: list[FaqPair]) -> list[FaqPair]:  # type: ignore[override]
        before = len(items)
        filtered = [
            p
            for p in items
            if p.answer
            and p.question.strip().lower() != p.answer.strip().lower()
            and not any(pat.search(p.answer) for pat in JUNK_ANSWER_PATTERNS)
        ]
        removed = before - len(filtered)
        if removed > 0:
            print(f"[extraction] Filtered out {removed} low-quality pair(s)")
        return filtered
