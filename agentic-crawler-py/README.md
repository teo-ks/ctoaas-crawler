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
cp .env.example .env  # fill in your credentials
docker build -t crawler .
```

## Usage

Defaults: `--mode faq`, `--format json`. Both flags are optional — omit them to use the defaults.

```bash
# FAQ extraction — JSON, save to disk (--mode faq --format json implied)
docker run --rm --env-file .env -v $(pwd)/output:/app/output crawler python -m src.main https://ask.gov.sg/ecda --save

# General content extraction — Markdown
docker run --rm --env-file .env -v $(pwd)/output:/app/output crawler python -m src.main https://ask.gov.sg/ecda --format md --mode general --save

# No disk write — output returned via stdout (---RESULT--- marker)
docker run --rm --env-file .env crawler python -m src.main https://ask.gov.sg/ecda

# Limit crawl depth
docker run --rm --env-file .env -v $(pwd)/output:/app/output crawler python -m src.main https://example.com --max-requests 5 --save

# Smoke-test the container
python scripts/test_container.py
python scripts/test_container.py --url https://example.com --mode general
```

The smoke test runs a short crawl (`--max-requests 5`), captures the JSON from the container's stdout, and validates at least one result was extracted.

## Output

`run_crawler()` always returns the rendered output (`str` for JSON/FAQ Markdown, `dict[filename, str]` for general Markdown). Disk writes are opt-in — pass `--save` to also write to disk. When deployed as a service, omit `--save` and consume the return value directly.

| Mode | Format | File (with `--save`) |
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
