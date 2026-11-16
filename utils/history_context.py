"""Bound model context without mutating persisted chat logs."""

HISTORY_LIMIT = 200
RECENT_FULL_MESSAGES = 50
OLD_TEXT_LIMIT = 500


def context_messages(rows: list) -> list:
    """Keep the newest 50 intact, truncate older text and omit old image payloads."""
    rows = rows[-HISTORY_LIMIT:]
    cutoff = max(0, len(rows) - RECENT_FULL_MESSAGES)
    result = []
    for index, row in enumerate(rows):
        if index >= cutoff:
            result.append(row)
            continue
        values = list(row)
        if len(values[3]) > OLD_TEXT_LIMIT:
            values[3] = values[3][:OLD_TEXT_LIMIT] + "… [сокращено]"
        values[4] = None
        values[5] = None
        result.append(tuple(values))
    return result
