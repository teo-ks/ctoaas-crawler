# agentic-crawler-py

Python rewrite of the agentic FAQ crawler, with an added **general content extraction** mode for RAG pipelines.

## Features

- **FAQ mode** (`--mode faq`): extracts Q&A pairs from FAQ/help pages
- **General mode** (`--mode general`): extracts all named sections from every page for use in a RAG knowledge base
- **JSON or Markdown output** (`--format json|md`)
- Supports Anthropic direct or any OpenAI-compatible endpoint (LiteLLM, OpenRouter, etc.)
- Accordion/pagination expansion before extraction
- LLM-powered discovery fallback when heuristics find no links

## Setup

```bash
cd agentic-crawler-py

# Install with pip (or uv)
pip install -e .

# Install Playwright browser
playwright install chromium

# Copy and fill in your API key
cp .env.example .env
```

## Usage

```bash
# FAQ extraction — JSON output (default)
python -m src.main https://ask.gov.sg/ecda

# FAQ extraction — Markdown output
python -m src.main https://ask.gov.sg/ecda --format md

# General content extraction — Markdown (RAG-optimised)
python -m src.main https://ask.gov.sg/ecda --mode general --format md

# Limit crawl depth
python -m src.main https://example.com --max-requests 50
```

## Output

| Mode | Format | Output |
|------|--------|--------|
| faq | json | `output/<domain>.json` |
| faq | md | `output/<domain>.md` |
| general | json | `output/<domain>.json` |
| general | md | `output/<domain>/<page>.md` (one file per page, YAML front matter) |

## Environment variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key (used when `LLM_BASE_URL` is not set) |
| `LLM_BASE_URL` | Base URL for OpenAI-compatible endpoint |
| `LLM_API_KEY` | API key for OpenAI-compatible endpoint |
| `LLM_MODEL` | Primary model (default: `claude-haiku-4-5-20251001`) |
| `LLM_FALLBACK_MODEL` | Fallback model (default: `claude-sonnet-4-6`) |
| `APIFY_PROXY_PASSWORD` | Apify proxy password for Cloudflare-protected sites |

## Project structure

```
src/
├── main.py                   # CLI entry point
├── llm/client.py             # LLMClient, AnthropicClient, OpenAICompatibleClient, CostTracker
├── utils/
│   ├── html_cleaner.py       # BeautifulSoup4 HTML cleaning
│   └── output_writer.py      # JSON / Markdown output writer
├── schemas/
│   ├── faq.py                # Pydantic: FaqPair, FaqOutput
│   └── general.py            # Pydantic: ContentSection, PageContent, GeneralOutput
├── agents/
│   ├── base.py               # BaseExtractionAgent ABC
│   ├── faq_agent.py          # FaqExtractionAgent
│   ├── general_agent.py      # GeneralExtractionAgent
│   └── discovery_agent.py    # Link discovery helpers
└── crawler/
    └── crawler.py            # PlaywrightCrawler orchestrator
```
