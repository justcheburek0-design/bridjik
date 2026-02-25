"""Markdown to HTML converter for Telegram."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

_md = MarkdownIt().enable("strikethrough")

_TAG_MAP = {
    "<strong>": "<b>",
    "</strong>": "</b>",
    "<em>": "<i>",
    "</em>": "</i>",
    "<del>": "<s>",
    "</del>": "</s>",
}


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown formatting to Telegram HTML."""
    if not text:
        return text

    html = _md.render(text).strip()

    html = re.sub(r"<p>(.*?)</p>", r"\1", html, flags=re.DOTALL)
    html = re.sub(r"<li>(.*?)</li>", r"• \1", html, flags=re.DOTALL)
    html = re.sub(r"<[uo]l>(.*?)</[uo]l>", r"\1", html, flags=re.DOTALL)
    html = re.sub(r"<h[1-6]>(.*?)</h[1-6]>", r"<b>\1</b>", html, flags=re.DOTALL)

    for src, dst in _TAG_MAP.items():
        html = html.replace(src, dst)

    return html.strip()
