# Agentic FAQ Scraper

Extracts FAQ question-and-answer pairs from any website using Playwright for browser automation and an LLM for content extraction.

Instead of fragile CSS selectors, the scraper sends cleaned page HTML to an LLM which identifies and structures Q&A pairs regardless of how the site is built.

## How it works

Every page in the queue goes through the same steps:

1. **Expand** — Playwright clicks all "View more" / "Load more" buttons and expands all accordion items so hidden content is in the DOM
2. **Enqueue** — Same-domain links matching FAQ-like paths (`/faq`, `/help`, `/questions/`, `topic=`) are added to the crawl queue
3. **Extract** — Cleaned HTML is sent to the LLM extraction agent, which returns structured `{ question, answer, category }` pairs. If the page has no Q&A content the agent returns an empty list — no special page-type detection needed
4. **Discover** (fallback) — If step 2 found no links *and* step 3 found no pairs, the LLM discovery agent scans the page to find FAQ links that didn't match the heuristic filter

The crawler runs until the queue is empty or the `maxRequests` limit is reached. Duplicate questions (same normalised text from different pages) are discarded automatically.

## Prerequisites

- Node.js 20+
- An LLM API key (Anthropic direct, or any LiteLLM / OpenAI-compatible endpoint)

## Installation

```bash
cd agentic-crawler
npm install
```

Playwright browsers are installed automatically via the `postinstall` script.

## Configuration

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

### Option A — Direct Anthropic

```env
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5-20251001
LLM_FALLBACK_MODEL=claude-sonnet-4-6
```

### Option B — LiteLLM or any OpenAI-compatible proxy

Set `LLM_BASE_URL` to your proxy root. The scraper will automatically use the OpenAI-compatible client instead of the Anthropic SDK.

```env
LLM_BASE_URL=http://localhost:4000        # LiteLLM local
# LLM_BASE_URL=https://openrouter.ai/api/v1  # OpenRouter

LLM_API_KEY=your_litellm_or_proxy_key    # falls back to ANTHROPIC_API_KEY if unset
LLM_MODEL=bedrock-claude-haiku-3         # model name as your proxy knows it
LLM_FALLBACK_MODEL=google-gemini-3-flash
```

> **Note:** You can provide the full endpoint URL (e.g. `.../chat/completions`) — the scraper strips trailing path segments automatically so the SDK can append its own paths correctly.

### Optional — Proxy for Cloudflare-protected sites

```env
APIFY_PROXY_PASSWORD=your_apify_proxy_password
```

When set, all requests are routed through Apify residential proxies. Leave unset for sites that don't require it.

## Usage

```bash
# Scrape the default test site (ask.gov.sg/ecda)
npm start

# Scrape any URL
npx tsx src/index.ts https://example.com/faq

# Watch mode (reruns on file changes, useful during development)
npm run dev https://example.com/faq
```

Output is saved to `output/<domain>.json`.

## Output format

```json
{
  "domain": "ask.gov.sg",
  "startUrl": "https://ask.gov.sg/ecda",
  "scrapedAt": "2026-03-13T04:23:21.948Z",
  "totalPairs": 165,
  "pairs": [
    {
      "question": "What clearances are required for relief staff?",
      "answer": "Staff are not required to undergo medical screening again if...",
      "category": "Staff",
      "url": "https://ask.gov.sg/questions/..."
    }
  ]
}
```

| Field | Description |
|---|---|
| `question` | The FAQ question, extracted verbatim |
| `answer` | The full answer text |
| `category` | Section/category heading, if present on the page |
| `url` | Source URL the pair was extracted from |

## Project structure

```
src/
├── index.ts                  Entry point — reads URL from CLI args
├── llm/
│   └── client.ts             LLM abstraction (Anthropic or OpenAI-compatible)
├── utils/
│   └── htmlCleaner.ts        Strips noise elements before sending to LLM
├── schemas/
│   └── faq.ts                Zod schemas for FAQ pairs and output
├── agents/
│   ├── extractionAgent.ts    Sends cleaned HTML to LLM, parses Q&A pairs
│   └── discoveryAgent.ts     Finds FAQ links on unknown sites (heuristic + LLM)
└── crawler/
    └── faqCrawler.ts         Crawlee orchestrator — pagination, queueing, output
```

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (if no `LLM_BASE_URL`) | — | Anthropic API key for direct usage |
| `LLM_BASE_URL` | No | — | OpenAI-compatible proxy URL. When set, switches to proxy mode |
| `LLM_API_KEY` | No | `ANTHROPIC_API_KEY` | API key for the proxy (if different from Anthropic key) |
| `LLM_MODEL` | No | `claude-haiku-4-5-20251001` | Primary model for extraction |
| `LLM_FALLBACK_MODEL` | No | `claude-sonnet-4-6` | Fallback model if primary fails |
| `APIFY_PROXY_PASSWORD` | No | — | Routes traffic through Apify residential proxies |

## Cost

Using Claude Haiku, most FAQ pages cost under **$0.02 per page** to extract. A full 100-page site typically costs less than **$2 total**.

The scraper automatically falls back to the (more expensive) fallback model only when the primary model returns an unparseable response.
