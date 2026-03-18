"""Writes extracted data to JSON or Markdown files."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..schemas.faq import FaqOutput
from ..schemas.general import GeneralOutput


def write_output(
    data: FaqOutput | GeneralOutput,
    fmt: str,  # "json" | "md"
    output_dir: str = "./output",
) -> None:
    """Dispatch to JSON or Markdown writer based on fmt."""
    os.makedirs(output_dir, exist_ok=True)
    if fmt == "md":
        _write_markdown(data, output_dir)
    else:
        _write_json(data, output_dir)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _write_json(data: FaqOutput | GeneralOutput, output_dir: str) -> None:
    safe_domain = data.domain.replace(".", "_")
    path = Path(output_dir) / f"{safe_domain}.json"
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    print(f"[output] Saved JSON → {path}")


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def _write_markdown(data: FaqOutput | GeneralOutput, output_dir: str) -> None:
    if isinstance(data, FaqOutput):
        _write_faq_markdown(data, output_dir)
    else:
        _write_general_markdown(data, output_dir)


def _write_faq_markdown(data: FaqOutput, output_dir: str) -> None:
    """Single .md file, sections per category, each Q&A as ### Question / Answer."""
    safe_domain = data.domain.replace(".", "_")
    path = Path(output_dir) / f"{safe_domain}.md"

    lines: list[str] = [f"# FAQ — {data.domain}\n"]

    # Group by category
    by_category: dict[str, list] = {}
    for pair in data.pairs:
        cat = pair.category or "General"
        by_category.setdefault(cat, []).append(pair)

    for cat, pairs in by_category.items():
        lines.append(f"\n## {cat}\n")
        for pair in pairs:
            lines.append(f"### {pair.question}\n")
            lines.append(f"{pair.answer}\n")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[output] Saved Markdown → {path}")


def _write_general_markdown(data: GeneralOutput, output_dir: str) -> None:
    """One .md file per page under output/<domain>/, RAG-optimised with YAML front matter."""
    domain_dir = Path(output_dir) / data.domain.replace(".", "_")
    domain_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(data.pages):
        # Build a safe filename from the URL path
        from urllib.parse import urlparse
        url_path = urlparse(page.url).path.strip("/").replace("/", "_") or "index"
        safe_name = f"{i:04d}_{url_path[:80]}.md"
        path = domain_dir / safe_name

        lines: list[str] = [
            "---",
            f"url: {page.url}",
            f"title: {page.title}",
            f"domain: {data.domain}",
            f"scraped_at: {data.scraped_at}",
            "---",
            "",
            f"# {page.title}",
            "",
        ]

        for section in page.sections:
            lines.append(f"## {section.heading}")
            lines.append("")
            lines.append(section.content)
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    print(f"[output] Saved {len(data.pages)} Markdown pages → {domain_dir}/")
