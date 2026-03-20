"""Source citation formatting for social media first-comments."""

from __future__ import annotations


def format_sources_comment(sources: list[dict]) -> str:
    """Format a list of source dicts into a concise citation comment.

    Accepts both new-style entries (with ``url``) and legacy entries (without).
    """
    if not sources:
        return ""

    lines = ["Sources:"]
    for entry in sources:
        source = entry.get("source", "").strip()
        url = entry.get("url", "").strip()
        if not source:
            continue
        if url:
            lines.append(f"{source} - {url}")
        else:
            lines.append(source)

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)
