"""Pydantic schemas for general content extraction."""

from __future__ import annotations

from pydantic import BaseModel


class ContentSection(BaseModel):
    heading: str
    content: str  # prose text for this section
    url: str | None = None


class PageContent(BaseModel):
    title: str
    sections: list[ContentSection]
    url: str


class GeneralOutput(BaseModel):
    domain: str
    start_url: str
    scraped_at: str
    total_pages: int
    pages: list[PageContent]
