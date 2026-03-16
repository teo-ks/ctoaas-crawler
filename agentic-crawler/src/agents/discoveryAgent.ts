import * as cheerio from 'cheerio';
import { type LLMClient, type CostTracker, DEFAULT_MODEL } from '../llm/client.js';

const FAQ_KEYWORDS = /faq|help|support|question|answer|guidance|query|enquir|knowledgebase/i;

const DISCOVERY_PROMPT = `You are a web navigation agent. Given a list of links from a webpage, identify all URLs that likely lead to FAQ or help content.

Return ONLY valid JSON in this format (no markdown, no explanation):
{"faqUrls": ["https://...", "https://..."]}

If no FAQ-related links are found, return: {"faqUrls": []}

FAQ indicators in URLs or link text: faq, help, support, questions, answers, guidance, query, enquiry, knowledgebase`;

/**
 * Discovers FAQ-related links on a page.
 * Results are restricted to the same hostname as pageUrl — never follows
 * cross-domain links, which prevents the crawler drifting to unrelated sites.
 *
 * Strategy:
 * 1. Fast heuristic pass — checks href + link text against FAQ keywords (free, no LLM)
 * 2. LLM pass — if heuristics find nothing, sends same-domain links to the LLM
 */
export async function discoverFaqLinks(
  pageUrl: string,
  rawHtml: string,
  llmClient: LLMClient,
  costTracker?: CostTracker
): Promise<string[]> {
  const pageHostname = new URL(pageUrl).hostname;
  const allLinks = extractLinks(pageUrl, rawHtml);

  // Restrict to same domain before anything else
  const sameDomainLinks = allLinks.filter((l) => {
    try { return new URL(l.href).hostname === pageHostname; } catch { return false; }
  });

  if (sameDomainLinks.length === 0) return [];

  // --- Pass 1: heuristic (no LLM cost) ---
  const heuristic = sameDomainLinks.filter(
    (l) => FAQ_KEYWORDS.test(l.href) || FAQ_KEYWORDS.test(l.text)
  );
  if (heuristic.length > 0) {
    return dedupe(heuristic.map((l) => l.href));
  }

  // --- Pass 2: LLM discovery (same-domain links only) ---
  const linkList = sameDomainLinks
    .slice(0, 100)
    .map((l) => `${l.text || '(no text)'} → ${l.href}`)
    .join('\n');

  const messages = [
    {
      role: 'user' as const,
      content: `${DISCOVERY_PROMPT}\n\nPage: ${pageUrl}\n\nLinks:\n${linkList}`,
    },
  ];

  try {
    const response = await llmClient.complete(messages, DEFAULT_MODEL);
    costTracker?.record(response.usage, DEFAULT_MODEL, `${pageUrl} (discovery)`);

    const cleaned = response.content.replace(/```(?:json)?\n?/g, '').trim();
    const parsed = JSON.parse(cleaned) as { faqUrls?: unknown[] };
    if (!Array.isArray(parsed.faqUrls)) return [];

    // Final guard: ensure LLM didn't hallucinate off-domain URLs
    return parsed.faqUrls
      .filter((u): u is string => typeof u === 'string')
      .filter((u) => { try { return new URL(u).hostname === pageHostname; } catch { return false; } });
  } catch (err) {
    console.error('[discovery] Failed to parse LLM response:', err);
    return [];
  }
}

function extractLinks(pageUrl: string, html: string): { href: string; text: string }[] {
  const $ = cheerio.load(html);
  const links: { href: string; text: string }[] = [];

  $('a[href]').each((_, el) => {
    const raw = $(el).attr('href') ?? '';
    const text = $(el).text().trim();

    if (!raw || raw.startsWith('#') || raw.startsWith('mailto:') || raw.startsWith('tel:')) {
      return;
    }
    try {
      const absolute = new URL(raw, pageUrl).href;
      links.push({ href: absolute, text });
    } catch {
      // skip malformed URLs
    }
  });

  return links;
}

function dedupe(urls: string[]): string[] {
  return [...new Set(urls)];
}
