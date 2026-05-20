"""Graph operations — wikilink parsing, edge building, and Personalized PageRank.

PPR implementation adapted from GAAMA (MIT License, Swarna Kamal Paul 2026).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Sequence

WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilink]] targets from Markdown content."""
    return WIKILINK_PATTERN.findall(content)


def build_edges_from_wikilinks(
    node_id: str,
    content: str,
    name_to_id: dict[str, str],
) -> list[tuple[str, str, str, float]]:
    """Parse wikilinks from content and resolve to (source, target, type, weight) edges.

    Only creates edges for targets that exist in name_to_id mapping.
    """
    targets = extract_wikilinks(content)
    edges = []
    for target_name in targets:
        target_id = name_to_id.get(target_name)
        if target_id and target_id != node_id:
            edges.append((node_id, target_id, "links_to", 1.0))
    return edges


# Adapted from GAAMA (MIT) — Personalized PageRank
def personalized_pagerank(
    edges: Sequence[tuple[str, str, float]],
    seed_weights: dict[str, float],
    alpha: float = 0.85,
    max_iterations: int = 200,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """Compute Personalized PageRank on a local subgraph.

    Args:
        edges: List of (source_id, target_id, weight) tuples.
        seed_weights: Initial teleport distribution (node_id -> weight).
        alpha: Damping factor (probability of following an edge vs teleporting).
        max_iterations: Maximum power iterations.
        tolerance: Convergence threshold (L1 norm of score delta).

    Returns:
        Dict of node_id -> PPR score, max-normalized to [0, 1].
    """
    if not seed_weights:
        return {}

    total_seed = sum(seed_weights.values())
    if total_seed <= 0:
        return {nid: 0.0 for nid in seed_weights}
    v: dict[str, float] = {nid: w / total_seed for nid, w in seed_weights.items()}

    node_ids: set[str] = set(v.keys())
    out_edges: dict[str, list[tuple[str, float]]] = {}
    for source_id, target_id, weight in edges:
        node_ids.add(source_id)
        node_ids.add(target_id)
        w = max(0.0, float(weight))
        out_edges.setdefault(source_id, []).append((target_id, w))

    out_degree: dict[str, float] = {}
    for nid, targets in out_edges.items():
        out_degree[nid] = sum(w for _, w in targets)
    for nid in node_ids:
        out_degree.setdefault(nid, 0.0)

    for nid in node_ids:
        v.setdefault(nid, 0.0)

    in_contrib: dict[str, list[tuple[str, float]]] = {nid: [] for nid in node_ids}
    for source_id, targets in out_edges.items():
        deg = out_degree[source_id]
        if deg <= 0:
            continue
        for target_id, w in targets:
            in_contrib[target_id].append((source_id, w / deg))

    r = dict(v)
    for _ in range(max_iterations):
        sink_mass = sum(r.get(i, 0.0) for i in node_ids if out_degree[i] <= 0)
        r_new = {}
        for j in node_ids:
            incoming = (1.0 - alpha + alpha * sink_mass) * v[j]
            for i, frac in in_contrib.get(j, []):
                incoming += alpha * r.get(i, 0.0) * frac
            r_new[j] = incoming
        diff = sum(abs(r_new.get(n, 0) - r.get(n, 0)) for n in node_ids)
        r = r_new
        if diff < tolerance:
            break

    max_score = max(r.values()) if r else 0.0
    if max_score <= 0:
        return r
    return {nid: r[nid] / max_score for nid in node_ids}


def get_subgraph_bfs(
    node_id: str,
    get_neighbors_fn,
    depth: int = 2,
) -> set[str]:
    """BFS traversal from a starting node to a given depth.

    Args:
        node_id: Starting node.
        get_neighbors_fn: Callable(node_id) -> list[str] of neighbor IDs.
        depth: Maximum hops from starting node.

    Returns:
        Set of all node IDs reachable within `depth` hops (including start).
    """
    visited: set[str] = {node_id}
    frontier: set[str] = {node_id}

    for _ in range(depth):
        next_frontier: set[str] = set()
        for nid in frontier:
            for neighbor in get_neighbors_fn(nid):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    return visited
