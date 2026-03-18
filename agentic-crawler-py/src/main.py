"""CLI entry point for agentic-crawler-py."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from .llm.client import CostTracker, DEFAULT_MODEL, FALLBACK_MODEL, create_llm_client
from .crawler.crawler import run_crawler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Agentic web crawler for FAQ and general content extraction",
    )
    parser.add_argument("url", help="Start URL to crawl")
    parser.add_argument(
        "--mode",
        choices=["faq", "general"],
        default="faq",
        help="Extraction mode (default: faq)",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["json", "md"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=500,
        metavar="N",
        help="Maximum number of pages to crawl (default: 500)",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Directory to write output files (default: ./output)",
    )
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    llm_mode = (
        f"OpenAI-compatible → {os.getenv('LLM_BASE_URL')}"
        if os.getenv("LLM_BASE_URL")
        else "Anthropic (direct)"
    )

    print("")
    print("🕷️  Agentic Crawler (Python)")
    print("─" * 55)
    print(f"📍 Target:    {args.url}")
    print(f"🎯 Mode:      {args.mode}")
    print(f"📄 Format:    {args.fmt}")
    print(f"🤖 LLM mode:  {llm_mode}")
    print(f"📦 Model:     {DEFAULT_MODEL}")
    print(f"📦 Fallback:  {FALLBACK_MODEL}")
    print("─" * 55)
    print("")

    llm_client = create_llm_client()
    cost_tracker = CostTracker()

    result = await run_crawler(
        start_url=args.url,
        mode=args.mode,
        fmt=args.fmt,
        max_requests=args.max_requests,
        output_dir=args.output_dir,
        llm_client=llm_client,
        cost_tracker=cost_tracker,
        proxy_url=os.getenv("PROXY_URL"),
    )

    cost_tracker.summary()

    if args.mode == "faq":
        print(f"\n✅ Done — extracted {result.total_pairs} FAQ pairs")  # type: ignore[union-attr]
    else:
        print(f"\n✅ Done — extracted {result.total_pages} pages")  # type: ignore[union-attr]


if __name__ == "__main__":
    asyncio.run(main())
