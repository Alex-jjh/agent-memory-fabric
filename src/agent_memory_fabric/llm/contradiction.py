"""Contradiction detection — LLM-based semantic comparison of new info vs existing memories."""

from __future__ import annotations

import re

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.llm.prompts import (
    CONTRADICTION_DETECTION_SYSTEM,
    CONTRADICTION_DETECTION_USER,
)
from agent_memory_fabric.llm.provider import LLMProvider

_MAX_CONTENT_LENGTH = 2000


def _sanitize_for_prompt(text: str) -> str:
    """Sanitize text before inserting into LLM prompt to prevent injection."""
    text = text[:_MAX_CONTENT_LENGTH]
    text = text.replace("</new_info>", "").replace("</existing_memory>", "")
    text = re.sub(r"</?(?:new_info|existing_memory|system|instruction)>", "", text)
    return text


def detect_contradictions(
    new_content: str,
    existing_nodes: list[MemoryNode],
    provider: LLMProvider,
    max_comparisons: int = 20,
) -> list[tuple[MemoryNode, str]]:
    """Detect which existing memories are contradicted by new information.

    Args:
        new_content: The new information to check against.
        existing_nodes: Candidate memories to compare against.
        provider: LLM provider for contradiction detection.
        max_comparisons: Maximum number of LLM calls (cost control).

    Returns:
        List of (contradicted_node, reason) tuples.
    """
    contradictions: list[tuple[MemoryNode, str]] = []

    candidates = existing_nodes[:max_comparisons]

    for node in candidates:
        user_prompt = CONTRADICTION_DETECTION_USER.format(
            new_content=_sanitize_for_prompt(new_content),
            existing_content=_sanitize_for_prompt(node.content),
        )

        try:
            response = provider.complete(CONTRADICTION_DETECTION_SYSTEM, user_prompt)
        except Exception:
            continue
        response = response.strip()

        if response.upper().startswith("YES"):
            reason = response[4:].strip(": ") if len(response) > 3 else "contradicted"
            contradictions.append((node, reason))

    return contradictions
