"""Text utilities."""

import hashlib
import re


def shorten(text: str, limit: int = 700) -> str:
    """Shorten text to specified limit."""
    text = (text or "").strip()
    return (text[:limit] + "...") if len(text) > limit else text


def truncate_text(text: str, max_length: int = 2000) -> str:
    """
    Truncate text to max_length, trying to respect [[...]] tags.

    If truncating in the middle of a tag:
    - If the tag starts after max_length - 50, we just cut before the tag.
    - If the tag is long and crosses the boundary, we cut before the tag.
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    # Find all tags
    # Tags format: [[type:payload]]
    tag_re = re.compile(
        r"\[\[(photo|sticker|kb|guess|voice):([^\]]+)\]\]", re.IGNORECASE
    )

    # Check if cut point is inside a tag
    cut_point = max_length

    # Find the last tag that starts before cut_point
    last_tag_start = -1
    last_tag_end = -1

    for match in tag_re.finditer(text):
        if match.start() < cut_point:
            last_tag_start = match.start()
            last_tag_end = match.end()
        else:
            break

    # If cut_point splits a tag (start < cut_point < end)
    if last_tag_start != -1 and last_tag_end > cut_point:
        # We are cutting inside a tag. Safe bet: cut before the tag.
        cut_point = last_tag_start

    # Truncate
    result = text[:cut_point].rstrip()
    if len(result) < len(text):
        result += "..."

    return result


def hash_text(text: str) -> str:
    """Create short deterministic hash for text."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def get_hour_string(hours: int) -> str:
    """Format hours as human-readable string in Russian."""
    if hours == 1:
        return "1 час"
    elif hours in (2, 3, 4):
        return f"{hours} часа"
    else:
        return f"{hours} часов"
