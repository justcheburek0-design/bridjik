"""Markdown to HTML converter for Telegram."""

import re


def markdown_to_telegram_html(text: str) -> str:
    """Convert Markdown formatting to Telegram HTML.

    Supports:
    - **bold** or __bold__ → <b>bold</b>
    - *italic* or _italic_ → <i>italic</i>
    - `code` → <code>code</code>
    - ```code block``` → <pre>code block</pre>
    - ~~strikethrough~~ → <s>strikethrough</s>
    - [text](url) → <a href="url">text</a>

    Args:
        text: Text with Markdown formatting

    Returns:
        Text with Telegram HTML formatting
    """
    if not text:
        return text

    result = text

    # Code blocks first (```...```)
    # Handle multiline code blocks
    result = re.sub(r"```(?:\w+)?\n?(.*?)```", r"<pre>\1</pre>", result, flags=re.DOTALL)

    # Inline code (`...`)
    result = re.sub(r"`([^`]+)`", r"<code>\1</code>", result)

    # Bold (**...**) - must be before italic
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result)

    # Bold (__...__)
    result = re.sub(r"__(.+?)__", r"<b>\1</b>", result)

    # Italic (*...*)
    result = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", result)

    # Italic (_..._) - be careful with underscores in words
    result = re.sub(r"(?<![a-zA-Z0-9])_([^_]+?)_(?![a-zA-Z0-9])", r"<i>\1</i>", result)

    # Strikethrough (~~...~~)
    result = re.sub(r"~~(.+?)~~", r"<s>\1</s>", result)

    # Links [text](url)
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', result)

    return result
