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

_LINE_BREAK_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"</p>\s*<p>", flags=re.IGNORECASE)
_PARAGRAPH_WRAPPER_RE = re.compile(r"<p>(.*?)</p>", flags=re.DOTALL | re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"<li>(.*?)</li>", flags=re.DOTALL | re.IGNORECASE)
_LIST_RE = re.compile(r"</?[uo]l>", flags=re.IGNORECASE)
_HEADER_RE = re.compile(r"<h[1-6]>(.*?)</h[1-6]>", flags=re.DOTALL | re.IGNORECASE)
_REDUNDANT_TAG_PATTERNS = (
    (re.compile(r"(<(b|i|s|code|pre)>)\s*\1", flags=re.IGNORECASE), r"\1"),
    (re.compile(r"(</(b|i|s|code|pre)>)\s*\1", flags=re.IGNORECASE), r"\1"),
)


def _collapse_redundant_tags(html: str) -> str:
    """Collapse duplicated adjacent Telegram-supported tags."""
    previous = None
    while html != previous:
        previous = html
        for pattern, replacement in _REDUNDANT_TAG_PATTERNS:
            html = pattern.sub(replacement, html)
    return html


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown formatting to Telegram HTML."""
    if not text:
        return text

    html = _md.render(text).strip()
    html = _LINE_BREAK_RE.sub("\n", html)
    html = _PARAGRAPH_RE.sub("\n\n", html)
    html = _PARAGRAPH_WRAPPER_RE.sub(r"\1", html)
    html = _LIST_ITEM_RE.sub(r"- \1\n", html)
    html = _LIST_RE.sub("", html)
    html = _HEADER_RE.sub(r"<b>\1</b>", html)

    for src, dst in _TAG_MAP.items():
        html = html.replace(src, dst)

    html = _collapse_redundant_tags(html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()
