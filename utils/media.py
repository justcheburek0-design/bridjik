"""Media utilities."""

from __future__ import annotations

import base64


def make_data_url(image_bytes: bytes, mime_type: str | None = None) -> str:
    """Create a base64 data URL for image bytes."""
    mt = (mime_type or "image/jpeg").strip().lower()
    if not mt.startswith("image/"):
        mt = f"image/{mt}" if "/" not in mt else mt
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mt};base64,{b64}"
