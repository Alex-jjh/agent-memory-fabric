"""Injection security: prevent prompt injection via stored memory content."""

from __future__ import annotations

import re

CONTEXT_TAGS = re.compile(
    r"</?(?:learned_context|system|instruction|tool_result|memory|function_calls"
    r"|antml|invoke|result|parameter|assistant|user|human|thinking|tool_use)"
    r"[^>]*>",
    re.IGNORECASE,
)


def escape_context_tags(text: str) -> str:
    """Replace XML-like tags that could break injection structure.

    Prevents stored memory text from closing or opening XML blocks
    when injected into a prompt.
    """
    return CONTEXT_TAGS.sub(
        lambda m: m.group(0).replace("<", "&lt;").replace(">", "&gt;"),
        text,
    )


def frame_untrusted(text: str, source: str = "memory") -> str:
    """Wrap external/untrusted data with boundary markers.

    Escapes dangerous tags first, then wraps with boundary markers.
    """
    sanitized = escape_context_tags(text)
    return f"[BEGIN UNTRUSTED:{source}]\n{sanitized}\n[END UNTRUSTED:{source}]"
