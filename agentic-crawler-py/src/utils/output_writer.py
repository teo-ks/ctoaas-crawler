"""Writes or renders extracted data as JSON or Markdown."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from ..schemas.faq import FaqOutput
from ..schemas.general import GeneralOutput


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_output(
    data: FaqOutput | GeneralOutput,
    fmt: str,  # "json" | "md"
) -> str | dict[str, str]:
    """Render data to a string (or dict of filename → string for general+md).

    Returns:
        str   — for fmt=json (JSON string) or fmt=md with FaqOutput
        dict  — for fmt=md with GeneralOutput: {filename: markdown_content}
    """
    if fmt == "md":
        if isinstance(data, FaqOutput):
            return _render_faq_markdown(data)
        return _render_general_markdown(data)
    return data.model_dump_json(indent=2)


def write_output(
    data: FaqOutput | GeneralOutput,
    fmt: str,  # "json" | "md"
    output_dir: str = "./output",
    rendered: str | dict[str, str] | None = None,
) -> None:
    """Write pre-rendered (or freshly rendered) output to disk."""
    os.makedirs(output_dir, exist_ok=True)
    if rendered is None:
        rendered = render_output(data, fmt)

    if fmt == "md" and isinstance(rendered, dict):
        # general+md: one file per page
        domain_dir = Path(output_dir) / data.domain.replace(".", "_")
        domain_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in rendered.items():
            (domain_dir / filename).write_text(content, encoding="utf-8")
        print(f"[output] Saved {len(rendered)} Markdown pages → {domain_dir}/")
    elif fmt == "md":
        safe_domain = data.domain.replace(".", "_")
        path = Path(output_dir) / f"{safe_domain}.md"
        path.write_text(rendered, encoding="utf-8")  # type: ignore[arg-type]
        print(f"[output] Saved Markdown → {path}")
    else:
        safe_domain = data.domain.replace(".", "_")
        path = Path(output_dir) / f"{safe_domain}.json"
        path.write_text(rendered, encoding="utf-8")  # type: ignore[arg-type]
        print(f"[output] Saved JSON → {path}")


# ---------------------------------------------------------------------------
# Renderers — return strings, never touch disk
# ---------------------------------------------------------------------------


def _render_faq_markdown(data: FaqOutput) -> str:
    lines: list[str] = [f"# FAQ — {data.domain}\n"]

    by_category: dict[str, list] = {}
    for pair in data.pairs:
        cat = pair.category or "General"
        by_category.setdefault(cat, []).append(pair)

    for cat, pairs in by_category.items():
        lines.append(f"\n## {cat}\n")
        for pair in pairs:
            lines.append(f"### {pair.question}\n")
            lines.append(f"{pair.answer}\n")

    return "\n".join(lines)


def _render_general_markdown(data: GeneralOutput) -> dict[str, str]:
    """Returns {filename: markdown_content} for each page."""
    pages: dict[str, str] = {}

    for i, page in enumerate(data.pages):
        url_path = urlparse(page.url).path.strip("/").replace("/", "_") or "index"
        filename = f"{i:04d}_{url_path[:80]}.md"

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

        pages[filename] = "\n".join(lines)

    return pages
