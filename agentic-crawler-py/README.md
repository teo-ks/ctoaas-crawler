# agentic-crawler-py

An agentic web crawler that extracts structured content from websites. Supports **FAQ extraction** for Q&A pairs and **general content extraction** for RAG pipelines, with JSON or Markdown output.

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

# Create virtualenv and install dependencies
uv venv .venv
uv pip install -e .

# Install Playwright browser
.venv/bin/playwright install chromium

# Copy and fill in your credentials
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
| `LLM_BASE_URL` | Base URL for OpenAI-compatible endpoint (e.g. `https://openrouter.ai/api/v1`) |
| `LLM_API_KEY` | API key for OpenAI-compatible endpoint |
| `LLM_MODEL` | Primary model (default: `google/gemini-3-flash-preview`) |
| `LLM_FALLBACK_MODEL` | Fallback model (default: `anthropic/claude-haiku-4.5`) |
| `PROXY_URL` | Optional HTTP/HTTPS proxy for Cloudflare-protected sites (e.g. `http://user:pass@proxy.example.com:8080`) |

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
│   ├── base_extraction_agent.py   # BaseExtractionAgent ABC
│   ├── faq_extraction_agent.py    # FaqExtractionAgent
│   ├── general_extraction_agent.py # GeneralExtractionAgent
│   └── discovery_agent.py         # Link discovery helpers
└── crawler/
    └── crawler.py            # PlaywrightCrawler orchestrator
```
