import { PlaywrightCrawler, log as crawleeLog } from 'crawlee';
import { type Page } from 'playwright';
import * as fs from 'fs/promises';
import * as path from 'path';
import { type LLMClient, type CostTracker } from '../llm/client.js';
import { extractFaqPairs } from '../agents/extractionAgent.js';
import { discoverFaqLinks } from '../agents/discoveryAgent.js';
import { type FaqPair, type FaqOutput } from '../schemas/faq.js';


// Matches "View more", "Load more", "Show all", "See more" etc.
// Used for pagination buttons that append more items to the current page.
const PAGINATION_BUTTON_RE = /^(view|load|show|see)\s+(more|all)$/i;

// Nav/chrome elements — accordion buttons inside these are never FAQ items
const NAV_SELECTOR = 'nav, header, footer, [role="navigation"], [role="banner"], [role="contentinfo"]';

export interface CrawlConfig {
  startUrl: string;
  llmClient: LLMClient;
  costTracker?: CostTracker;
  maxRequests?: number;
  outputDir?: string;
  /** Optional Apify proxy password for Cloudflare-protected sites */
  apifyProxyPassword?: string;
}

export async function runFaqCrawler(config: CrawlConfig): Promise<FaqPair[]> {
  const {
    startUrl,
    llmClient,
    costTracker,
    maxRequests = 500,
    outputDir = './output',
    apifyProxyPassword,
  } = config;

  const startDomain = new URL(startUrl).hostname;
  const allPairs: FaqPair[] = [];
  const seenQuestions = new Set<string>();

  await fs.mkdir(outputDir, { recursive: true });

  const proxyConfig = apifyProxyPassword
    ? { proxyUrls: [`http://groups-RESIDENTIAL:${apifyProxyPassword}@proxy.apify.com:8000`] }
    : undefined;

  const crawler = new PlaywrightCrawler({
    ...(proxyConfig ? { proxyConfiguration: proxyConfig as any } : {}),
    maxRequestRetries: 3,
    maxRequestsPerCrawl: maxRequests,
    requestHandlerTimeoutSecs: 120,

    async requestHandler({ page, request, enqueueLinks, log }) {
      const url = request.url;
      log.info(`Processing: ${url}`);

      await expandAll(page, log);

      const enqueued = await enqueueLinks({
        selector: 'a[href]',
        transformRequestFunction: sameDomainFaqFilter(startDomain),
      });
      log.info(`Enqueued ${enqueued.processedRequests.length} same-domain FAQ links`);

      const html = await page.content();
      const pairs = await extractFaqPairs(html, url, llmClient, costTracker);
      savePairs(pairs, url, allPairs, seenQuestions, log);

      // No links and no pairs — try the discovery agent as a last resort
      if (enqueued.processedRequests.length === 0 && pairs.length === 0) {
        log.info('No links and no pairs — running discovery agent...');
        const faqLinks = await discoverFaqLinks(url, html, llmClient, costTracker);
        if (faqLinks.length > 0) {
          log.info(`Discovery found ${faqLinks.length} same-domain FAQ links`);
          await crawler.addRequests(faqLinks.map((u) => ({ url: u })));
        }
      }
    },

    failedRequestHandler({ request, log }) {
      log.error(`Failed after retries: ${request.url}`);
    },
  });

  await crawler.addRequests([{ url: startUrl }]);
  await crawler.run();

  const safeDomain = startDomain.replace(/\./g, '_');
  const outputFile = path.join(outputDir, `${safeDomain}.json`);

  const output: FaqOutput = {
    domain: startDomain,
    startUrl,
    scrapedAt: new Date().toISOString(),
    totalPairs: allPairs.length,
    pairs: allPairs,
  };

  await fs.writeFile(outputFile, JSON.stringify(output, null, 2));
  crawleeLog.info(`💾 Saved ${allPairs.length} pairs → ${outputFile}`);

  return allPairs;
}

// ---------------------------------------------------------------------------
// Saves extracted pairs, deduplicating by normalised question text
// ---------------------------------------------------------------------------
function savePairs(
  pairs: FaqPair[],
  url: string,
  allPairs: FaqPair[],
  seen: Set<string>,
  log: { info: (m: string) => void }
): void {
  for (const pair of pairs) {
    const key = pair.question.toLowerCase().trim();
    if (!seen.has(key)) {
      seen.add(key);
      allPairs.push({ ...pair, url });
      log.info(`✅ ${pair.question.slice(0, 70)}`);
    }
  }
}

// ---------------------------------------------------------------------------
// Shared enqueueLinks filter — same domain + FAQ-related path patterns
// ---------------------------------------------------------------------------
function sameDomainFaqFilter(startDomain: string) {
  return function (req: { url: string }) {
    try {
      if (new URL(req.url).hostname !== startDomain) return false;
    } catch {
      return false;
    }
    const u = req.url.toLowerCase();
    if (
      u.includes('/questions/') ||
      u.includes('/faq') ||
      u.includes('/help') ||
      u.includes('topic=')
    ) {
      return req;
    }
    return false;
  };
}

// ---------------------------------------------------------------------------
// Master expand — runs on every non-question page before link enqueue / extract
// ---------------------------------------------------------------------------
async function expandAll(page: Page, log: { info: (msg: string) => void }): Promise<void> {
  await clickPaginationButtons(page, log);
  await expandCollapsedAccordions(page, log);
}

// ---------------------------------------------------------------------------
// Repeatedly clicks "View more" / "Load more" / "Show all" style buttons
// until none remain. These paginate lists by appending more items.
// ---------------------------------------------------------------------------
async function clickPaginationButtons(
  page: Page,
  log: { info: (msg: string) => void }
): Promise<void> {
  let totalClicks = 0;

  while (totalClicks < 50) {
    // Re-query each iteration so we pick up buttons revealed by previous clicks
    const buttons = await page.locator('button:visible').all();
    let clicked = false;

    for (const btn of buttons) {
      const text = ((await btn.textContent()) ?? '').trim();
      if (PAGINATION_BUTTON_RE.test(text)) {
        await btn.click();
        await page.waitForTimeout(1_500);
        totalClicks++;
        log.info(`Clicked pagination button "${text}" (${totalClicks})`);
        clicked = true;
        break; // restart with fresh DOM after each click
      }
    }

    if (!clicked) break;
  }
}

// ---------------------------------------------------------------------------
// Expands collapsed accordions in the main content area.
//
// Two-step strategy for cross-library compatibility:
//   Step 1 — Click each button via Playwright (correct for React/Radix/Vue state machines)
//   Step 2 — Force-show remaining hidden controlled panels via DOM manipulation
//             (catches single-mode accordions where only one item can be open,
//              and non-standard libraries that use aria-controls without React)
// ---------------------------------------------------------------------------
async function expandCollapsedAccordions(
  page: Page,
  log: { info: (msg: string) => void }
): Promise<void> {
  // Count collapsed non-nav accordion buttons
  const collapsedCount: number = await page.evaluate((navSel) => {
    return Array.from(document.querySelectorAll('button[aria-expanded="false"]'))
      .filter((el) => !el.closest(navSel))
      .length;
  }, NAV_SELECTOR);

  if (collapsedCount === 0) {
    // Also handle <details> elements even if no aria-expanded buttons found
    await openDetailsElements(page);
    return;
  }

  // Step 1: Click each button via Playwright (handles multi-mode Radix, Vue, etc.)
  // We click index 0 each time because the DOM shifts as items expand.
  let clicked = 0;
  while (clicked < Math.min(collapsedCount, 100)) {
    const didClick: boolean = await page.evaluate((navSel) => {
      const btn = Array.from(document.querySelectorAll('button[aria-expanded="false"]'))
        .find((el) => !el.closest(navSel));
      if (btn) { (btn as HTMLElement).click(); return true; }
      return false;
    }, NAV_SELECTOR);

    if (!didClick) break;
    await page.waitForTimeout(80); // enough for React to batch-process
    clicked++;
  }

  // Brief settle after all clicks
  if (clicked > 0) {
    await page.waitForTimeout(400);
    log.info(`Clicked ${clicked} accordion button(s)`);
  }

  // Step 2: Force-show any still-hidden controlled panels (single-mode fallback).
  // Finds aria-controls targets that are hidden and makes them visible.
  const forceShown: number = await page.evaluate((navSel) => {
    let count = 0;
    document.querySelectorAll('button[aria-expanded="false"][aria-controls]').forEach((btn) => {
      if (btn.closest(navSel)) return;
      const panelId = btn.getAttribute('aria-controls');
      const panel = panelId ? document.getElementById(panelId) : null;
      if (panel) {
        panel.removeAttribute('hidden');
        (panel as HTMLElement).style.display = '';
        (panel as HTMLElement).style.height = 'auto';
        (panel as HTMLElement).style.overflow = 'visible';
        btn.setAttribute('aria-expanded', 'true');
        count++;
      }
    });
    return count;
  }, NAV_SELECTOR);

  if (forceShown > 0) {
    log.info(`Force-revealed ${forceShown} single-mode accordion panel(s)`);
  }

  await openDetailsElements(page);
}

// ---------------------------------------------------------------------------
// Opens all collapsed <details> elements (native HTML accordion)
// ---------------------------------------------------------------------------
async function openDetailsElements(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.querySelectorAll('details:not([open])').forEach((d) => {
      d.setAttribute('open', '');
    });
  });
}
