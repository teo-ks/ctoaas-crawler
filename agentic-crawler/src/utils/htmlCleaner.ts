import * as cheerio from 'cheerio';

const NOISE_SELECTORS = [
  'script',
  'style',
  'svg',
  'img',
  'noscript',
  'iframe',
  'head',
  'header',
  'footer',
  'nav',
  '[aria-hidden="true"]',
  '.cookie-banner',
  '.advertisement',
  '.sidebar',
].join(', ');

/**
 * Strips noise elements and returns the main content HTML.
 * Keeps the HTML structure so the LLM can infer Q&A nesting.
 */
export function cleanHtml(rawHtml: string): string {
  const $ = cheerio.load(rawHtml);

  $(NOISE_SELECTORS).remove();

  // Prefer the main content container; fall back to body
  const main = $('main, article, [role="main"], #content, .content, #main').first();
  const content = main.length ? main.html() : $('body').html();

  return (content ?? '')
    .replace(/<!--[\s\S]*?-->/g, '')  // strip HTML comments
    .replace(/[ \t]{2,}/g, ' ')       // collapse inline whitespace
    .replace(/\n{3,}/g, '\n\n')       // collapse blank lines
    .trim();
}

/**
 * Rough token estimate: 1 token ≈ 4 characters.
 * Used to guard against sending oversized payloads to the LLM.
 */
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}
