"""HTML sanitization utilities."""

from __future__ import annotations

import re

import bleach

ALLOWED_TAGS = {"a", "b", "strong", "i", "em", "code", "s", "strike", "del", "u", "pre"}
ALLOWED_ATTRS = {"a": ["href"]}
_LINE_BREAK_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_PARAGRAPH_RE = re.compile(r"</p>\s*<p>", flags=re.IGNORECASE)
_PARAGRAPH_WRAPPER_RE = re.compile(r"</?p>", flags=re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"<li>(.*?)</li>", flags=re.DOTALL | re.IGNORECASE)
_LIST_RE = re.compile(r"</?[uo]l>", flags=re.IGNORECASE)
_REDUNDANT_TAG_PATTERNS = (
    (re.compile(r"(<(b|i|s|code|pre)>)\s*\1", flags=re.IGNORECASE), r"\1"),
    (re.compile(r"(</(b|i|s|code|pre)>)\s*\1", flags=re.IGNORECASE), r"\1"),
)


def _normalize_telegram_html(text: str) -> str:
    """Normalize unsupported HTML constructs before sanitizing."""
    normalized = _LINE_BREAK_RE.sub("\n", text)
    normalized = _PARAGRAPH_RE.sub("\n\n", normalized)
    normalized = _PARAGRAPH_WRAPPER_RE.sub("", normalized)
    normalized = _LIST_ITEM_RE.sub(r"- \1\n", normalized)
    normalized = _LIST_RE.sub("", normalized)

    previous = None
    while normalized != previous:
        previous = normalized
        for pattern, replacement in _REDUNDANT_TAG_PATTERNS:
            normalized = pattern.sub(replacement, normalized)

    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def remove(text: str) -> str:
    """Remove unsafe tags and normalize HTML formatting."""
    if not text:
        return ""

    normalized = _normalize_telegram_html(text)
    cleaned = bleach.clean(
        normalized,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
    )
    return cleaned.strip()
