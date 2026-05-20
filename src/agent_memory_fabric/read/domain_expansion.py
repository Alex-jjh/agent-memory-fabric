"""Domain expansion: discover related memories via tag overlap and tool scoping."""

from __future__ import annotations

from agent_memory_fabric.core.node import MemoryNode


def find_related_by_tags(
    anchor_nodes: list[MemoryNode],
    all_nodes: list[MemoryNode],
    min_tag_overlap: int = 2,
    exclude_ids: set[str] | None = None,
) -> list[MemoryNode]:
    """Find memories sharing tags with anchor nodes.

    Returns nodes from all_nodes that share at least min_tag_overlap tags
    with any anchor node, excluding anchor nodes themselves.
    """
    exclude = exclude_ids or set()
    anchor_ids = {n.id for n in anchor_nodes}
    exclude = exclude | anchor_ids

    anchor_tags: set[str] = set()
    for node in anchor_nodes:
        anchor_tags.update(t.lower() for t in node.tags)

    related: list[MemoryNode] = []
    for node in all_nodes:
        if node.id in exclude:
            continue
        node_tags = {t.lower() for t in node.tags}
        overlap = len(node_tags & anchor_tags)
        if overlap >= min_tag_overlap:
            related.append(node)

    return related


def filter_by_domain(
    memories: list[MemoryNode],
    active_domain: str | None = None,
) -> list[MemoryNode]:
    """Filter memories by applicable_domains field.

    Returns memories that either:
    - Have no domain restriction (applicable_domains is empty = universal)
    - Include the active_domain in their applicable_domains list
    """
    if not active_domain:
        return memories

    domain_lower = active_domain.lower()
    return [
        m for m in memories
        if not m.applicable_domains or domain_lower in [d.lower() for d in m.applicable_domains]
    ]
