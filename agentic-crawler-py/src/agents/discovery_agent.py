"""Discovery agent — finds FAQ/help links on a page (heuristic + LLM fallback)."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..llm.client import CostTracker, LLMClient, LLMMessage, DEFAULT_MODEL

FAQ_KEYWORDS = re.compile(
    r"faq|help|support|question|answer|guidance|query|enquir|knowledgebase", re.IGNORECASE
)

DISCOVERY_PROMPT = """You are a web navigation agent. Given a list of links from a webpage, identify all URLs that likely lead to FAQ or help content.

Return ONLY valid JSON in this format (no markdown, no explanation):
{"faqUrls": ["https://...", "https://..."]}

If no FAQ-related links are found, return: {"faqUrls": []}

FAQ indicators in URLs or link text: faq, help, support, questions, answers, guidance, query, enquiry, knowledgebase"""


async def discover_faq_links(
    page_url: str,
    raw_html: str,
    llm_client: LLMClient,
    cost_tracker: CostTracker | None = None,
) -> list[str]:
    """
    Discover FAQ-related links on a page.

    Strategy:
    1. Fast heuristic pass — checks href + link text against FAQ keywords (free, no LLM)
    2. LLM pass — if heuristics find nothing, sends same-domain links to the LLM
    """
    page_hostname = urlparse(page_url).hostname
    all_links = _extract_links(page_url, raw_html)

    same_domain = [
        lnk for lnk in all_links
        if _safe_hostname(lnk["href"]) == page_hostname
    ]

    if not same_domain:
        return []

    # Pass 1: heuristic (no LLM cost)
    heuristic = [
        lnk for lnk in same_domain
        if FAQ_KEYWORDS.search(lnk["href"]) or FAQ_KEYWORDS.search(lnk["text"])
    ]
    if heuristic:
        return list(dict.fromkeys(lnk["href"] for lnk in heuristic))

    # Pass 2: LLM discovery
    link_list = "\n".join(
        f"{lnk['text'] or '(no text)'} → {lnk['href']}"
        for lnk in same_domain[:100]
    )
    messages = [
        LLMMessage(
            role="user",
            content=f"{DISCOVERY_PROMPT}\n\nPage: {page_url}\n\nLinks:\n{link_list}",
        )
    ]

    try:
        response = await llm_client.complete(messages, DEFAULT_MODEL)
        if cost_tracker:
            cost_tracker.record(response.usage, DEFAULT_MODEL, f"{page_url} (discovery)")

        cleaned = re.sub(r"```(?:json)?\n?", "", response.content).strip()
        parsed = json.loads(cleaned)
        if not isinstance(parsed.get("faqUrls"), list):
            return []

        return [
            u for u in parsed["faqUrls"]
            if isinstance(u, str) and _safe_hostname(u) == page_hostname
        ]
    except Exception as e:
        print(f"[discovery] Failed to parse LLM response: {e}")
        return []


async def discover_general_links(
    page_url: str,
    raw_html: str,
) -> list[str]:
    """Return all same-domain links (used by general mode)."""
    page_hostname = urlparse(page_url).hostname
    all_links = _extract_links(page_url, raw_html)
    return list(dict.fromkeys(
        lnk["href"] for lnk in all_links
        if _safe_hostname(lnk["href"]) == page_hostname
    ))


FAQ_PATH_PATTERNS = ("/questions/", "/faq", "/help", "topic=")


def extract_faq_path_links(page_url: str, raw_html: str) -> list[str]:
    """Extract same-domain links whose URL matches FAQ path patterns (no LLM).

    Used as the primary link enqueue step in FAQ mode, replacing
    context.enqueue_links so we get visibility into what is found.
    """
    page_hostname = urlparse(page_url).hostname
    all_links = _extract_links(page_url, raw_html)
    results: list[str] = []
    for lnk in all_links:
        href = lnk["href"]
        if _safe_hostname(href) != page_hostname:
            continue
        lower = href.lower()
        if any(pat in lower for pat in FAQ_PATH_PATTERNS):
            results.append(href)
    return list(dict.fromkeys(results))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_links(page_url: str, html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    links: list[dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        text = a.get_text(strip=True)
        if not raw or raw.startswith("#") or raw.startswith("mailto:") or raw.startswith("tel:"):
            continue
        try:
            absolute = urljoin(page_url, raw)
            links.append({"href": absolute, "text": text})
        except Exception:
            pass
    return links


def _safe_hostname(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except Exception:
        return None
