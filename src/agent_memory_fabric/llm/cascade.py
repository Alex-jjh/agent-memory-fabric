"""Cascade contradiction reasoning: identify secondary memories affected by a state change.

When a direct contradiction is detected (e.g., "moved from Shanghai to Sydney"),
this module identifies OTHER memories whose practical basis has changed
(e.g., commute routes, nearby restaurants, local contacts).

Inspired by CUP-Mem's "bucket bridge" concept (clean-room reimplementation).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from agent_memory_fabric.core.node import MemoryNode

if TYPE_CHECKING:
    from agent_memory_fabric.llm.provider import LLMProvider
    from agent_memory_fabric.storage.sqlite_store import SQLiteStore


_CASCADE_AFFECTED_DOMAINS_SYSTEM = """You analyze how a factual change affects other stored knowledge.

When a user's situation changes (e.g., moved cities, changed jobs, ended relationship),
identify which OTHER topics in their memory are likely affected.

Focus on practical dependencies:
- Location change → commute, nearby places, local weather, local contacts
- Job change → schedule, colleagues, tools, income
- Relationship change → shared activities, plans, living situation
- Health change → routines, capabilities, diet

Output ONLY valid JSON:
{"affected_domains": [{"keywords": ["keyword1", "keyword2"], "reason": "brief explanation"}]}

Rules:
- Max 3 affected domains
- Only include if the practical basis CLEARLY changed
- Keywords should be specific enough to find related memories
- Do NOT include the domain of the direct contradiction itself"""

_CASCADE_AFFECTED_DOMAINS_USER = """A memory was just archived because it was contradicted:

ARCHIVED (old, now stale): {archived_content}
NEW (current): {new_content}

What OTHER stored memories might now be invalid due to this change?
Identify affected domains with search keywords."""

_CASCADE_VALIDATE_SYSTEM = """Decide if a stored memory is likely invalid due to a recent change.

The user's situation changed. Given that change, is this specific memory still valid?

- YES: The memory's practical basis is broken by the change (it's now stale)
- NO: The memory is still valid despite the change

Respond with ONLY: YES: <reason> or NO: <reason>"""

_CASCADE_VALIDATE_USER = """CHANGE: {new_content} (this replaced: {archived_content})

MEMORY TO CHECK: {candidate_content}

Is this memory now invalid due to the change above?"""


def identify_affected_domains(
    new_content: str,
    archived_content: str,
    provider: "LLMProvider",
) -> list[dict]:
    """Identify secondary domains affected by a contradiction."""
    user_prompt = _CASCADE_AFFECTED_DOMAINS_USER.format(
        new_content=new_content[:500],
        archived_content=archived_content[:500],
    )

    try:
        response = provider.complete(_CASCADE_AFFECTED_DOMAINS_SYSTEM, user_prompt)
        response = response.strip()
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1:
            return []
        data = json.loads(response[start:end + 1])
        domains = data.get("affected_domains", [])
        return [d for d in domains[:3] if isinstance(d, dict) and d.get("keywords")]
    except Exception:
        return []


def find_cascade_candidates(
    affected_domains: list[dict],
    active_nodes: list[MemoryNode],
    sqlite_store: "SQLiteStore",
    max_per_domain: int = 5,
) -> list[MemoryNode]:
    """Search for memories in affected domains via FTS keywords."""
    candidates: list[MemoryNode] = []
    seen_ids: set[str] = set()

    for domain in affected_domains:
        keywords = domain.get("keywords", [])
        if not keywords:
            continue

        query = " OR ".join(f'"{k}"' for k in keywords[:5])
        try:
            fts_results = sqlite_store.search_fts(query, limit=max_per_domain)
            node_ids = {nid for nid, _ in fts_results}
            for node in active_nodes:
                if node.id in node_ids and node.id not in seen_ids:
                    candidates.append(node)
                    seen_ids.add(node.id)
        except Exception:
            continue

    return candidates


def validate_cascade_candidates(
    new_content: str,
    archived_content: str,
    candidates: list[MemoryNode],
    provider: "LLMProvider",
) -> list[tuple[MemoryNode, str]]:
    """Lightweight YES/NO check on each cascade candidate."""
    validated: list[tuple[MemoryNode, str]] = []

    for node in candidates:
        user_prompt = _CASCADE_VALIDATE_USER.format(
            new_content=new_content[:300],
            archived_content=archived_content[:300],
            candidate_content=node.content[:300],
        )

        try:
            response = provider.complete(_CASCADE_VALIDATE_SYSTEM, user_prompt)
            response = response.strip()
            if response.upper().startswith("YES"):
                reason = response[4:].strip(": ") if len(response) > 3 else "cascade invalidation"
                validated.append((node, reason))
        except Exception:
            continue

    return validated


def detect_cascade_contradictions(
    new_content: str,
    direct_archived: list[tuple[str, str]],
    active_nodes: list[MemoryNode],
    provider: "LLMProvider",
    sqlite_store: "SQLiteStore",
    max_cascade: int = 5,
) -> list[tuple[MemoryNode, str]]:
    """Full cascade pipeline: affected domains → candidates → validation.

    Args:
        new_content: The new information that triggered direct contradictions
        direct_archived: List of (node_id, archived_content) for directly archived nodes
        active_nodes: All currently active memory nodes
        provider: LLM provider for reasoning
        sqlite_store: For FTS search in affected domains
        max_cascade: Maximum cascade archival targets

    Returns:
        List of (node, reason) tuples for cascade-invalidated memories.
    """
    if not direct_archived:
        return []

    all_cascade: list[tuple[MemoryNode, str]] = []
    directly_archived_ids = {nid for nid, _ in direct_archived}

    for archived_id, archived_content in direct_archived[:2]:
        # Step 1: Identify affected domains
        domains = identify_affected_domains(new_content, archived_content, provider)
        if not domains:
            continue

        # Step 2: Find candidates in those domains
        remaining_active = [n for n in active_nodes if n.id not in directly_archived_ids]
        candidates = find_cascade_candidates(domains, remaining_active, sqlite_store)
        if not candidates:
            continue

        # Step 3: Validate each candidate
        validated = validate_cascade_candidates(new_content, archived_content, candidates, provider)
        all_cascade.extend(validated)

        if len(all_cascade) >= max_cascade:
            break

    return all_cascade[:max_cascade]
