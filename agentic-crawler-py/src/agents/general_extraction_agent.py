"""General content extraction agent — RAG-optimised output."""

from __future__ import annotations

import json
from typing import Any

from .base_extraction_agent import BaseExtractionAgent
from ..schemas.general import ContentSection, PageContent

_SYSTEM_PROMPT = """You are a precise content extraction agent. Your job is to extract structured content from HTML for use in a RAG (retrieval-augmented generation) knowledge base.

Rules:
- Only extract content that is explicitly present in the HTML — never infer or fabricate
- Extract every named section from the page (headings, sub-headings, labelled blocks)
- For each section, capture the full prose content under that heading
- Join multi-paragraph content with \\n\\n (two newlines)
- Include the page title if present
- Return ONLY valid JSON — no markdown fences, no explanation, nothing else

Output format:
{"title": "Page Title", "sections": [{"heading": "Section Name", "content": "Section prose..."}]}

If nothing extractable is found, return exactly: {"title": "", "sections": []}"""


class GeneralExtractionAgent(BaseExtractionAgent):
    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def parse_response(self, raw: str, url: str) -> list[PageContent]:
        try:
            cleaned = self.strip_fences(raw)
            parsed = json.loads(cleaned)

            title = parsed.get("title", "") or ""
            sections_raw = parsed.get("sections", [])

            if not isinstance(sections_raw, list):
                print(f"[extraction] Unexpected response shape for {url}")
                return []

            sections: list[ContentSection] = []
            for s in sections_raw:
                if not isinstance(s.get("heading"), str) or not isinstance(s.get("content"), str):
                    continue
                heading = s["heading"].strip()
                content = s["content"].strip()
                if heading and content:
                    sections.append(ContentSection(heading=heading, content=content))

            return [PageContent(title=title, sections=sections, url=url)]
        except Exception as e:
            print(f"[extraction] Failed to parse LLM response for {url}: {e}")
            print(f"[extraction] Raw response (first 500 chars): {raw[:500]}")
            return []

    def filter_quality(self, items: list[PageContent]) -> list[PageContent]:  # type: ignore[override]
        return [p for p in items if p.sections]
