"""HTML sanitization utilities."""

from __future__ import annotations

import bleach

ALLOWED_TAGS = {"a", "b", "strong", "i", "em", "code", "s", "strike", "del", "u", "pre"}
ALLOWED_ATTRS = {"a": ["href"]}


def remove(text: str) -> str:
    """Remove unsafe tags and normalize HTML formatting."""
    if not text:
        return ""
    return bleach.clean(text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True).strip()
