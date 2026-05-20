"""Memory injection formatting for LLM context windows."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import groupby

from agent_memory_fabric.core.node import MemoryNode, MemoryType
from agent_memory_fabric.core.security import escape_context_tags
from agent_memory_fabric.read.scorer import ScoredMemory

LEARNED_CONTEXT_START = "<learned_context>"
LEARNED_CONTEXT_END = "</learned_context>"

TYPE_DISPLAY_ORDER = [
    MemoryType.USER,
    MemoryType.FEEDBACK,
    MemoryType.PROJECT,
    MemoryType.REFERENCE,
    MemoryType.ENTITY,
]

TYPE_LABELS = {
    MemoryType.USER: "User Profile",
    MemoryType.FEEDBACK: "Preferences & Feedback",
    MemoryType.PROJECT: "Project Knowledge",
    MemoryType.REFERENCE: "Reference Information",
    MemoryType.ENTITY: "Related Entities",
}


def _format_age(node: MemoryNode) -> str:
    """Format time since last access as human-readable string."""
    now = datetime.now(timezone.utc)
    delta = now - node.last_accessed
    hours = delta.total_seconds() / 3600
    if hours < 24:
        return "today"
    days = int(hours / 24)
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}w ago"
    months = days // 30
    return f"{months}mo ago"


def _format_confidence(node: MemoryNode) -> str:
    """Format confidence as percentage."""
    conf = node.confidence_alpha / (node.confidence_alpha + node.confidence_beta)
    return f"{int(conf * 100)}%"


def _format_memory_line(sm: ScoredMemory) -> str:
    """Format a single memory as a bullet point with metadata."""
    node = sm.node
    content = escape_context_tags(node.content)
    age = _format_age(node)
    cert = _format_confidence(node)
    relevance = f"{int(sm.total_score * 100)}%"

    provenance = "inferred"
    for tag in node.tags:
        if tag.startswith("provenance:"):
            provenance = tag.split(":", 1)[1]
            break

    return f"- [{provenance}] [rel: {relevance}, cert: {cert}] [{age}] {content}"


def format_memories_xml(memories: list[ScoredMemory]) -> str:
    """Format scored memories as XML block for injection into user message."""
    if not memories:
        return ""

    sections: list[str] = []

    sorted_memories = sorted(memories, key=lambda m: TYPE_DISPLAY_ORDER.index(m.node.type)
                             if m.node.type in TYPE_DISPLAY_ORDER else 99)

    for mem_type, group in groupby(sorted_memories, key=lambda m: m.node.type):
        label = TYPE_LABELS.get(mem_type, mem_type.value.title())
        items = list(group)
        lines = [f"## {label}"]
        for sm in items:
            lines.append(_format_memory_line(sm))
        sections.append("\n".join(lines))

    body = "\n\n".join(sections)
    return f"{LEARNED_CONTEXT_START}\n# LEARNED CONTEXT\n\n{body}\n{LEARNED_CONTEXT_END}"


def inject_into_message(user_message: str, memories_xml: str) -> str:
    """Prepend memory context before the user's message content."""
    if not memories_xml:
        return user_message
    return f"{memories_xml}\n\n{user_message}"


def format_interpretation_rules() -> str:
    """Generate system prompt section with memory interpretation rules."""
    return """<memory_interpretation_rules>
When using memories from <learned_context>:
- [user explicit] preferences are standing instructions — follow them
- cert >= 80%: use directly without hedging
- cert 50-79%: use but hedge ("I recall that...", "Based on what I know...")
- cert < 50%: treat as hypothesis, offer to verify if user asks directly
- [user explicit] > [inferred] when conflicting
- Anti-patterns (cert < 60%) are guidance, not rules — never refuse a tool solely on a low-certainty anti-pattern
- Facts older than 2 weeks with cert < 70%: note potential staleness
- If ambiguous + low-confidence + user is asking directly: offer to verify
</memory_interpretation_rules>"""
