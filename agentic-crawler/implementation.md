# Agentic FAQ Scraper — Implementation Plan

## Goal

Dynamically scrape FAQ question-and-answer pairs from **any** website without writing
site-specific selectors. An LLM agent drives the extraction logic, making it resilient
to structural differences across sites.

---

## Why Agentic?

FAQ sections differ wildly across websites:
- Some are accordion components rendered with JavaScript
- Some live on `/faq`, others are embedded deep in `/support/help/general`
- Some use `<dl>/<dt>/<dd>`, others use custom React components
- Some require clicking "Show Answer" buttons before content is visible

A hardcoded selector-based scraper breaks the moment a site updates. An LLM agent
reads the page the way a human would and extracts Q&A pairs regardless of structure.

---

## Recommended Tech Stack

### Core

| Layer | Tool | Reason |
|---|---|---|
| Browser automation | **Playwright** (via Crawlee) | Full JS rendering, click interactions, proven from existing project |
| Crawling framework | **Crawlee** (TypeScript) | Already in this repo; handles queues, retries, concurrency |
| LLM extraction | **Claude Haiku 4.5** | Cheapest Claude model; fast enough for extraction tasks |
| LLM fallback | **Claude Sonnet 4.6** | For complex/ambiguous pages that Haiku struggles with |
| Schema validation | **Zod** | Strongly-typed output for FAQ pairs |
| Runtime | **Node.js / TypeScript** | Consistent with existing crawlee-crawler |

### Optional (for scale)

| Layer | Tool | Reason |
|---|---|---|
| Job queue | **BullMQ + Redis** | Parallelise scraping jobs across many URLs |
| Storage | **PostgreSQL** | Persist extracted Q&A pairs (Neon or Supabase for cheap hosted) |
| Proxy rotation | **Apify Proxy** or **Oxylabs** | For Cloudflare-protected sites (see crawlee_vs_apify.md) |

---

## Architecture

```
Input URL
    │
    ▼
┌─────────────────────────────────┐
│  Step 1: Discovery Agent        │  Uses Playwright to load the page,
│  "Find FAQ entry points"        │  then asks Claude: "Where is the FAQ
│                                 │  section? Give me the URLs or CSS
│                                 │  selectors to navigate to it."
└────────────┬────────────────────┘
             │  FAQ page URL(s)
             ▼
┌─────────────────────────────────┐
│  Step 2: Interaction Agent      │  Playwright clicks "expand" / "show
│  "Expand all answers"           │  answer" / accordion buttons so all
│                                 │  content is visible in the DOM.
└────────────┬────────────────────┘
             │  Fully-expanded HTML
             ▼
┌─────────────────────────────────┐
│  Step 3: Extraction Agent       │  Sends cleaned HTML to Claude with
│  "Extract Q&A pairs"            │  a structured output prompt.
│                                 │  Returns: { question, answer }[]
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Step 4: Validation + Storage   │  Zod validates schema.
│                                 │  Write to JSON / DB.
└─────────────────────────────────┘
```

---

## Agent Prompts (Sketch)

### Discovery Agent
```
You are a web navigation agent. Given the HTML of a website's homepage or sitemap,
identify all URLs or anchor links that are likely to contain FAQ content.
Return a JSON array of { url: string, confidence: "high"|"medium" }.
```

### Interaction Agent
```
You are a browser automation agent. Given a Playwright page object and the current
DOM, identify any collapsed FAQ items (accordions, "show more" buttons, etc.)
and return a list of CSS selectors to click in order to reveal all answers.
```

### Extraction Agent
```
You are a data extraction agent. Given the HTML of a FAQ page, extract all
question-and-answer pairs. Return a JSON array of:
{ question: string, answer: string, category?: string }
Do not infer or fabricate content. Only extract what is explicitly on the page.
```

---

## Cost Estimate (Claude API)

| Model | Input price | Output price |
|---|---|---|
| Haiku 4.5 | $0.80 / 1M tokens | $4.00 / 1M tokens |
| Sonnet 4.6 | $3.00 / 1M tokens | $15.00 / 1M tokens |

For most FAQ pages:
- Cleaned HTML ≈ 5,000–20,000 tokens per page
- At Haiku pricing: **< $0.02 per page**
- A 100-site batch ≈ **< $2.00 total**

Use Haiku by default; escalate to Sonnet only on retry/failure.

---

## Project Structure

```
agentic-crawler/
├── implementation.md        ← this file
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts             ← entry point, accepts URL input
│   ├── agents/
│   │   ├── discovery.ts     ← finds FAQ pages on a site
│   │   ├── interaction.ts   ← expands collapsed FAQ elements
│   │   └── extraction.ts    ← extracts Q&A pairs via Claude
│   ├── crawler/
│   │   └── playwrightCrawler.ts  ← Crawlee PlaywrightCrawler setup
│   ├── schemas/
│   │   └── faq.ts           ← Zod schema for { question, answer, category }
│   └── utils/
│       ├── htmlCleaner.ts   ← strips scripts/styles before sending to LLM
│       └── tokenCounter.ts  ← guards against oversized prompts
├── output/
│   └── *.json               ← scraped FAQ output per domain
└── .env                     ← ANTHROPIC_API_KEY
```

---

## Key Implementation Details

### 1. HTML Cleaning (Critical for Cost)
Before sending to Claude, strip all `<script>`, `<style>`, `<svg>`, `<img>` tags
and HTML comments. This reduces a typical page from ~80K tokens to ~5K tokens.
Use `node-html-parser` or `cheerio` for this.

### 2. Context Window Management
If cleaned HTML exceeds ~60K tokens, chunk it by top-level sections (`<section>`,
`<article>`, `<div id="faq">`) and run extraction on each chunk separately,
then merge results.

### 3. Retry with Escalation
```
Haiku extraction fails (empty result / malformed JSON)
    → retry once with Haiku + more explicit prompt
    → if still failing, escalate to Sonnet
    → if still failing, log for manual review
```

### 4. Deduplication
FAQ pairs often repeat across pages. Hash `question.toLowerCase().trim()` to
deduplicate before writing to storage.

---

## Skills to Install

These Claude Code skills will accelerate development:

```bash
# Playwright best practices — covers Crawlee + Playwright patterns
npx skills add currents-dev/playwright-best-practices-skill@playwright-best-practices

# Playwright website explorer — helps write the discovery + interaction agents
npx skills add github/awesome-copilot@playwright-explore-website

# Agentic browser patterns — LLM-driven browser automation patterns
npx skills add inference-sh/skills@agent-browser

# Claude API / Anthropic SDK — for wiring up Claude API calls in the agents
# (already available as built-in skill in this project)
```

---

## Getting Started (Once Ready to Build)

```bash
cd agentic-crawler
npm init -y
npm install crawlee playwright @anthropic-ai/sdk zod cheerio
npm install -D typescript @types/node tsx

# Set your API key
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# Run against a test URL
npx tsx src/index.ts --url https://example.com
```

---

## Open Questions / Decisions

- [ ] **Storage target**: JSON files (simple) vs PostgreSQL (queryable) — decide based on volume
- [ ] **Proxy strategy**: Start without proxies; add if Cloudflare blocking becomes an issue
- [ ] **Crawl depth**: Should the discovery agent follow pagination within FAQ sections?
- [ ] **Rate limiting**: Add per-domain delays to avoid bans (Crawlee handles this natively)
- [ ] **Anti-hallucination**: Add a post-extraction validator that checks each answer exists verbatim in the raw HTML
