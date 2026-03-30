"""PlaywrightCrawler orchestrator — supports FAQ and general modes (crawlee 1.x API)."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from crawlee._autoscaling.autoscaled_pool import ConcurrencySettings
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext

from ..agents.discovery_agent import (
    discover_faq_links,
    discover_general_links,
    extract_faq_path_links,
)
from ..agents.faq_extraction_agent import FaqExtractionAgent
from ..agents.general_extraction_agent import GeneralExtractionAgent
from ..llm.client import CostTracker, LLMClient
from ..schemas.faq import FaqOutput, FaqPair
from ..schemas.general import GeneralOutput, PageContent
from ..utils.output_writer import render_output, write_output

# Pagination buttons — "View more", "Load more", "Show all", "See more"
PAGINATION_BUTTON_RE = re.compile(r"^(view|load|show|see)\s+(more|all)$", re.IGNORECASE)
MAX_PAGINATION_CLICKS = 50

# Nav/chrome selectors
NAV_SELECTOR = "nav, header, footer, [role='navigation'], [role='banner'], [role='contentinfo']"


async def run_crawler(
    start_url: str,
    mode: str = "faq",  # "faq" | "general"
    fmt: str = "json",  # "json" | "md"
    max_requests: int = 500,
    output_dir: str = "./output",
    llm_client: LLMClient | None = None,
    cost_tracker: CostTracker | None = None,
    proxy_url: str | None = None,
    save_output: bool = False,
) -> str | dict[str, str]:
    if llm_client is None:
        from ..llm.client import create_llm_client

        llm_client = create_llm_client()
    if cost_tracker is None:
        cost_tracker = CostTracker()

    start_domain = urlparse(start_url).hostname or ""
    scraped_at = datetime.now(timezone.utc).isoformat()

    all_faq_pairs: list[FaqPair] = []
    all_pages: list[PageContent] = []
    seen_questions: set[str] = set()
    seen_urls: set[str] = set()

    faq_agent = FaqExtractionAgent(llm_client, cost_tracker)
    general_agent = GeneralExtractionAgent(llm_client, cost_tracker)

    # Build Playwright proxy dict directly — bypasses crawlee's ProxyConfiguration
    # which can mangle credentials containing special characters (e.g. commas in
    # Apify usernames like "groups-RESIDENTIAL,country-SG").
    playwright_proxy: dict | None = None
    if proxy_url:
        parsed = urlparse(proxy_url)
        playwright_proxy = {
            "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
            "username": parsed.username or "",
            "password": parsed.password or "",
        }

    browser_context_options: dict = {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if playwright_proxy:
        browser_context_options["proxy"] = playwright_proxy

    # Chromium inside Docker has no user-namespace sandbox — must disable it.
    # Detected via DOCKER_ENV=1 set in the Dockerfile.
    browser_launch_options: dict = {}
    if os.getenv("DOCKER_ENV"):
        browser_launch_options["args"] = ["--no-sandbox", "--disable-setuid-sandbox"]

    crawler = PlaywrightCrawler(
        max_request_retries=5,
        max_requests_per_crawl=max_requests,
        request_handler_timeout=timedelta(seconds=120),
        # Don't treat 403/429 as blocked sessions — 403 clears after cookies/JS
        # state is established; 429 just means slow down (handled by concurrency).
        ignore_http_error_status_codes=[403, 429],
        concurrency_settings=ConcurrencySettings(
            max_concurrency=3,
            desired_concurrency=2,
            max_tasks_per_minute=30,
        ),
        browser_launch_options=browser_launch_options or None,
        browser_new_context_options=browser_context_options,
    )

    async def _request_handler(context: PlaywrightCrawlingContext) -> None:
        url = context.request.url
        context.log.info(f"Processing: {url}")

        page = context.page

        # Expand accordions and pagination before reading HTML
        await _expand_all(page, context.log)

        html = await page.content()

        # Skip Cloudflare / bot-detection block pages
        if _is_blocked_page(html):
            context.log.warning(f"⛔ Blocked page detected (Cloudflare/bot block) — skipping {url}")
            return

        # Enqueue links
        if mode == "faq":
            faq_path_links = extract_faq_path_links(url, html)
            new_faq_links = [lnk for lnk in faq_path_links if lnk not in seen_urls]
            for lnk in new_faq_links:
                seen_urls.add(lnk)
            if new_faq_links:
                context.log.info(f"Enqueuing {len(new_faq_links)} FAQ path links")
                await context.add_requests(new_faq_links)
        else:
            # General mode: enqueue all same-domain links
            links = await discover_general_links(url, html)
            new_links = [lnk for lnk in links if lnk not in seen_urls]
            for lnk in new_links:
                seen_urls.add(lnk)
            if new_links:
                await context.add_requests(new_links)

        # Extract content
        if mode == "faq":
            pairs = await faq_agent.extract(html, url)
            added = 0
            for pair in pairs:
                key = pair.question.strip().lower()
                if key not in seen_questions:
                    seen_questions.add(key)
                    all_faq_pairs.append(pair.model_copy(update={"url": url}))
                    context.log.info(f"✅ {pair.question[:70]}")
                    added += 1
            context.log.info(f"Extracted {added} new FAQ pairs from {url}")

            # Discovery fallback — no links and no new pairs
            if added == 0 and not pairs:
                context.log.info("No pairs — running discovery agent...")
                faq_links = await discover_faq_links(url, html, llm_client, cost_tracker)
                if faq_links:
                    context.log.info(f"Discovery found {len(faq_links)} FAQ links")
                    await context.add_requests(faq_links)
        else:
            pages = await general_agent.extract(html, url)
            for page_content in pages:
                all_pages.append(page_content)
                context.log.info(
                    f"✅ {page_content.title[:70]} ({len(page_content.sections)} sections)"
                )

            # Discovery fallback for general mode
            if not pages:
                context.log.info("No sections extracted — trying discovery...")
                links = await discover_general_links(url, html)
                new_links = [lnk for lnk in links[:20] if lnk not in seen_urls]
                for lnk in new_links:
                    seen_urls.add(lnk)
                if new_links:
                    await context.add_requests(new_links)

    crawler.router.default_handler(_request_handler)
    await crawler.run([start_url])

    # Build output object
    if mode == "faq":
        result: FaqOutput | GeneralOutput = FaqOutput(
            domain=start_domain,
            start_url=start_url,
            scraped_at=scraped_at,
            total_pairs=len(all_faq_pairs),
            pairs=all_faq_pairs,
        )
        print(f"\n💾 Crawl complete — {len(all_faq_pairs)} FAQ pairs")
    else:
        result = GeneralOutput(
            domain=start_domain,
            start_url=start_url,
            scraped_at=scraped_at,
            total_pages=len(all_pages),
            pages=all_pages,
        )
        print(f"\n💾 Crawl complete — {len(all_pages)} pages")

    rendered = render_output(result, fmt=fmt)
    if save_output:
        write_output(result, fmt=fmt, output_dir=output_dir, rendered=rendered)
    return rendered


# ---------------------------------------------------------------------------
# Page interaction helpers
# ---------------------------------------------------------------------------


async def _expand_all(page, log) -> None:
    await _click_pagination_buttons(page, log)
    await _expand_collapsed_accordions(page, log)


async def _click_pagination_buttons(page, log) -> None:
    total_clicks = 0
    while total_clicks < MAX_PAGINATION_CLICKS:
        buttons = await page.locator("button:visible").all()
        clicked = False
        for btn in buttons:
            text = ((await btn.text_content()) or "").strip()
            if PAGINATION_BUTTON_RE.match(text):
                await btn.click()
                await page.wait_for_timeout(1500)
                total_clicks += 1
                log.info(f'Clicked pagination button "{text}" ({total_clicks})')
                clicked = True
                break
        if not clicked:
            break


async def _expand_collapsed_accordions(page, log) -> None:
    collapsed_count: int = await page.evaluate(
        """(navSel) => Array.from(document.querySelectorAll('button[aria-expanded="false"]'))
            .filter(el => !el.closest(navSel)).length""",
        NAV_SELECTOR,
    )

    if collapsed_count == 0:
        await _open_details_elements(page)
        return

    # Step 1: click each collapsed button
    clicked = 0
    while clicked < min(collapsed_count, 100):
        did_click: bool = await page.evaluate(
            """(navSel) => {
                const btn = Array.from(document.querySelectorAll('button[aria-expanded="false"]'))
                    .find(el => !el.closest(navSel));
                if (btn) { btn.click(); return true; }
                return false;
            }""",
            NAV_SELECTOR,
        )
        if not did_click:
            break
        await page.wait_for_timeout(80)
        clicked += 1

    if clicked > 0:
        await page.wait_for_timeout(400)
        log.info(f"Clicked {clicked} accordion button(s)")

    # Step 2: force-show remaining hidden panels (single-mode accordion fallback)
    force_shown: int = await page.evaluate(
        """(navSel) => {
            let count = 0;
            document.querySelectorAll('button[aria-expanded="false"][aria-controls]').forEach(btn => {
                if (btn.closest(navSel)) return;
                const panelId = btn.getAttribute('aria-controls');
                const panel = panelId ? document.getElementById(panelId) : null;
                if (panel) {
                    panel.removeAttribute('hidden');
                    panel.style.display = '';
                    panel.style.height = 'auto';
                    panel.style.overflow = 'visible';
                    btn.setAttribute('aria-expanded', 'true');
                    count++;
                }
            });
            return count;
        }""",
        NAV_SELECTOR,
    )

    if force_shown > 0:
        log.info(f"Force-revealed {force_shown} single-mode accordion panel(s)")

    await _open_details_elements(page)


async def _open_details_elements(page) -> None:
    await page.evaluate(
        "document.querySelectorAll('details:not([open])').forEach(d => d.setAttribute('open', ''))"
    )


# Cloudflare / bot-detection block page markers
_BLOCK_MARKERS = re.compile(
    r"(cloudflare-1xxx|error-1015|error 1015|banned you temporarily"
    r"|attention required|just a moment\.\.\.|cf-browser-verification"
    r"|cf_captcha_container|challenge-running)",
    re.IGNORECASE,
)


def _is_blocked_page(html: str) -> bool:
    return bool(_BLOCK_MARKERS.search(html[:8000]))
