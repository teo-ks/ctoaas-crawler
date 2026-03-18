"""HTML cleaning utilities — BeautifulSoup4 port of htmlCleaner.ts."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

NOISE_SELECTORS = [
    "script",
    "style",
    "svg",
    "img",
    "noscript",
    "iframe",
    "head",
    "header",
    "footer",
    "nav",
    '[aria-hidden="true"]',
    ".cookie-banner",
    ".advertisement",
    ".sidebar",
]


def clean_html(raw_html: str) -> str:
    """Strip noise elements and return the main content HTML."""
    soup = BeautifulSoup(raw_html, "lxml")

    for selector in NOISE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    # Prefer main content container; fall back to body
    main = soup.select_one("main, article, [role='main'], #content, .content, #main")
    content_tag = main or soup.body
    content = str(content_tag) if content_tag else ""

    # Strip HTML comments
    content = re.sub(r"<!--[\s\S]*?-->", "", content)
    # Collapse inline whitespace
    content = re.sub(r"[ \t]{2,}", " ", content)
    # Collapse blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return (len(text) + 3) // 4
