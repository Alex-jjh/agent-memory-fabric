"""Contradiction detection — LLM-based semantic comparison of new info vs existing memories."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from agent_memory_fabric.core.node import MemoryNode
from agent_memory_fabric.llm.prompts import (
    CONTRADICTION_DETECTION_SYSTEM,
    CONTRADICTION_DETECTION_USER,
)
from agent_memory_fabric.llm.provider import LLMProvider

if TYPE_CHECKING:
    from agent_memory_fabric.read.embeddings import EmbeddingProvider
    from agent_memory_fabric.storage.sqlite_store import SQLiteStore

_MAX_CONTENT_LENGTH = 2000


def _sanitize_for_prompt(text: str) -> str:
    """Sanitize text before inserting into LLM prompt to prevent injection."""
    text = text[:_MAX_CONTENT_LENGTH]
    text = text.replace("</new_info>", "").replace("</existing_memory>", "")
    text = re.sub(r"</?(?:new_info|existing_memory|system|instruction)>", "", text)
    return text


def _select_candidates_by_similarity(
    new_content: str,
    existing_nodes: list[MemoryNode],
    max_comparisons: int,
    embedding_provider: "EmbeddingProvider | None" = None,
    sqlite_store: "SQLiteStore | None" = None,
) -> list[MemoryNode]:
    """Select the most relevant candidates using vector/FTS similarity."""
    node_by_id = {n.id: n for n in existing_nodes}
    active_ids = set(node_by_id.keys())

    if embedding_provider and sqlite_store:
        try:
            embedding = embedding_provider.embed(new_content)
            results = sqlite_store.search_vector(embedding, limit=max_comparisons * 2)
            candidates = [node_by_id[nid] for nid, _ in results if nid in active_ids]
            if candidates:
                return candidates[:max_comparisons]
        except Exception:
            pass

    if sqlite_store:
        try:
            fts_results = sqlite_store.search_fts(new_content, limit=max_comparisons * 2)
            candidates = [node_by_id[nid] for nid, _ in fts_results if nid in active_ids]
            if candidates:
                return candidates[:max_comparisons]
        except Exception:
            pass

    return existing_nodes[:max_comparisons]


def detect_contradictions(
    new_content: str,
    existing_nodes: list[MemoryNode],
    provider: LLMProvider,
    max_comparisons: int = 20,
    embedding_provider: "EmbeddingProvider | None" = None,
    sqlite_store: "SQLiteStore | None" = None,
) -> list[tuple[MemoryNode, str]]:
    """Detect which existing memories are contradicted by new information.

    When embedding_provider or sqlite_store is available, uses semantic similarity
    to select the most relevant candidates for comparison rather than arbitrary order.
    """
    contradictions: list[tuple[MemoryNode, str]] = []

    candidates = _select_candidates_by_similarity(
        new_content, existing_nodes, max_comparisons,
        embedding_provider, sqlite_store,
    )

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
