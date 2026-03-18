"""Pydantic schemas for FAQ extraction."""

from __future__ import annotations

from pydantic import BaseModel


class FaqPair(BaseModel):
    question: str
    answer: str
    category: str | None = None
    url: str | None = None


class FaqOutput(BaseModel):
    domain: str
    start_url: str
    scraped_at: str
    total_pairs: int
    pairs: list[FaqPair]
