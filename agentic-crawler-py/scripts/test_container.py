#!/usr/bin/env python3
"""Smoke-test the Docker container without writing to disk.

Runs a short crawl (--max-requests 5) against a known site and validates
the returned JSON has at least one extracted result.

Usage:
    python scripts/test_container.py
    python scripts/test_container.py --url https://example.com --mode general
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the crawler Docker container")
    parser.add_argument("--url", default="https://ask.gov.sg/ecda", help="URL to crawl")
    parser.add_argument("--mode", choices=["faq", "general"], default="faq")
    parser.add_argument("--image", default="crawler", help="Docker image name")
    parser.add_argument("--max-requests", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"🐳 Testing container image '{args.image}'")
    print(f"   URL:  {args.url}")
    print(f"   Mode: {args.mode}")
    print(f"   Max requests: {args.max_requests}")
    print("")

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--env-file",
            ".env",
            args.image,
            "python",
            "-m",
            "src.main",
            args.url,
            "--mode",
            args.mode,
            "--format",
            "json",
            "--max-requests",
            str(args.max_requests),
            # No --save: output returned via ---RESULT--- marker
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("❌ Container exited with non-zero status")
        print("--- stderr ---")
        print(result.stderr[-2000:])
        sys.exit(1)

    # Extract output after the ---RESULT--- marker
    marker = "---RESULT---\n"
    if marker not in result.stdout:
        print("❌ ---RESULT--- marker not found in output")
        print("--- stdout (last 1000 chars) ---")
        print(result.stdout[-1000:])
        sys.exit(1)

    raw_output = result.stdout.split(marker)[1].strip()

    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON output: {e}")
        print("--- raw output ---")
        print(raw_output[:500])
        sys.exit(1)

    # Validate
    if args.mode == "faq":
        pairs = data.get("pairs", [])
        if not pairs:
            print("❌ No FAQ pairs extracted")
            sys.exit(1)
        print(f"✅ {len(pairs)} FAQ pairs extracted")
        print(f"   Domain:  {data.get('domain')}")
        print(f"   First Q: {pairs[0]['question'][:80]}")
    else:
        pages = data.get("pages", [])
        if not pages:
            print("❌ No pages extracted")
            sys.exit(1)
        total_sections = sum(len(p["sections"]) for p in pages)
        print(f"✅ {len(pages)} pages / {total_sections} sections extracted")
        print(f"   Domain: {data.get('domain')}")
        print(f"   First page: {pages[0]['title'][:80]}")


if __name__ == "__main__":
    main()
