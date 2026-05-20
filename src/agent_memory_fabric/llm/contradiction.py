"""Contradiction detection — LLM-based semantic comparison of new info vs existing memories."""

from __future__ import annotations

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.llm.prompts import (
    CONTRADICTION_DETECTION_SYSTEM,
    CONTRADICTION_DETECTION_USER,
)
from agent_memory_fabric.llm.provider import LLMProvider


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
            new_content=new_content,
            existing_content=node.content,
        )

        response = provider.complete(CONTRADICTION_DETECTION_SYSTEM, user_prompt)
        response = response.strip()

        if response.upper().startswith("YES"):
            reason = response[4:].strip(": ") if len(response) > 3 else "contradicted"
            contradictions.append((node, reason))

    return contradictions
