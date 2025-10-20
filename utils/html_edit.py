"""HTML sanitization utilities."""
import re
import html
from html.parser import HTMLParser
from urllib.parse import urlparse


ALLOWED_TAGS = {
    "a", "b", "strong", "i", "em", "code", "s", "strike", "del", "u", "pre"
}

SAFE_SCHEMES = {"http", "https"}


class WhitelistHTMLSanitizer(HTMLParser):
    """HTML sanitizer that only allows Telegram-compatible tags."""
    
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out = []
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            self.tag_stack.append(None)
            return

        if tag == "a":
            href = None
            for k, v in attrs:
                if k.lower() == "href":
                    v = html.unescape(v or "")
                    if _is_safe_href(v):
                        href = v
            if href:
                self.out.append(f'<a href="{html.escape(href, quote=True)}">')
                self.tag_stack.append("a")
            else:
                self.tag_stack.append(None)
            return

        if tag in ("pre", "code"):
            self.out.append(f"<{tag}>")
            self.tag_stack.append(tag)
            return

        self.out.append(f"<{tag}>")
        self.tag_stack.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if not self.tag_stack:
            return
        top = self.tag_stack.pop()
        if top == tag:
            self.out.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in ALLOWED_TAGS:
            self.out.append("<br>")

    def handle_data(self, data):
        self.out.append(data)

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")

    def get_html(self):
        return "".join(self.out)


def _is_safe_href(url: str) -> bool:
    """Check if URL is safe (http/https or relative)."""
    try:
        p = urlparse(url)
        return (p.scheme == "" and p.netloc == "" and url.startswith(("/", "#"))) or (p.scheme in SAFE_SCHEMES)
    except Exception:
        return False


def remove(text: str) -> str:
    """Remove unsafe tags and normalize HTML formatting."""
    if not text:
        return ""
    
    text = html.unescape(text)
    parser = WhitelistHTMLSanitizer()
    parser.feed(text)
    sanitized = parser.get_html()
    
    return sanitized.strip()

