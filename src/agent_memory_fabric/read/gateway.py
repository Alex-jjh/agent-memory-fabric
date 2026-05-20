"""Proactive Retrieval Gateway — orchestrates the full retrieval pipeline.

Pipeline:
1. Abstain check (skip if greeting/short/irrelevant)
2. FTS5 keyword retrieval
3. Vector similarity retrieval (if embeddings available)
4. Graph proximity via PPR (if entities detected)
5. Multi-signal scoring with all active signals
6. Staleness filter (exclude Archived/Expired)
7. Budget allocation (hot/warm/cold tiers)
"""

from __future__ import annotations

from agent_memory_fabric.core.config import AMFConfig, RetrieverConfig
from agent_memory_fabric.core.node import LifecycleState, MemoryNode
from agent_memory_fabric.read.abstain import AbstainGate
from agent_memory_fabric.read.embeddings import EmbeddingProvider, cosine_similarity
from agent_memory_fabric.read.scorer import MultiSignalScorer, ScoredMemory
from agent_memory_fabric.storage.graph import extract_wikilinks, personalized_pagerank
from agent_memory_fabric.storage.sqlite_store import SQLiteStore


class ProactiveGateway:
    """Entry point for proactive memory retrieval on each user message.

    Coordinates abstain gate, multi-source retrieval, scoring, and filtering.
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        scorer: MultiSignalScorer,
        config: RetrieverConfig | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.sqlite_store = sqlite_store
        self.scorer = scorer
        self.config = config or RetrieverConfig()
        self.embedding_provider = embedding_provider
        self.abstain_gate = AbstainGate()

    def retrieve(
        self,
        message: str,
        candidates: list[MemoryNode],
        scope: str | None = None,
        top_k: int | None = None,
        include_archived: bool = False,
    ) -> list[ScoredMemory]:
        """Full retrieval pipeline. Returns scored memories or empty if abstaining."""
        top_k = top_k or self.config.top_k

        if self.abstain_gate.should_abstain(message):
            return []

        # Scope filter
        if scope:
            candidates = [n for n in candidates if n.project == scope or n.project is None]

        # Signal 1: FTS5 keyword scores
        fts_results = self.sqlite_store.search_fts(message, limit=top_k * 5)
        fts_scores = {nid: score for nid, score in fts_results}

        # Signal 4: Vector similarity (if provider available)
        vector_scores: dict[str, float] = {}
        if self.embedding_provider:
            query_embedding = self.embedding_provider.embed(message)
            vec_results = self.sqlite_store.search_vector(query_embedding, limit=top_k * 3)
            if vec_results:
                max_dist = max(d for _, d in vec_results) if vec_results else 1.0
                min_dist = min(d for _, d in vec_results)
                dist_range = max_dist - min_dist
                if dist_range > 0:
                    vector_scores = {
                        nid: 1.0 - (dist - min_dist) / dist_range
                        for nid, dist in vec_results
                    }
                else:
                    vector_scores = {nid: 1.0 for nid, _ in vec_results}

        # Signal 5: Graph proximity via PPR
        graph_scores: dict[str, float] = {}
        mentioned_names = extract_wikilinks(message)
        if mentioned_names:
            all_nodes = self.sqlite_store.get_all_nodes()
            name_to_id = {r["name"]: r["id"] for r in all_nodes}
            seed_weights = {}
            for name in mentioned_names:
                if name in name_to_id:
                    seed_weights[name_to_id[name]] = 1.0
            if seed_weights:
                all_edges = self.sqlite_store.get_all_edges()
                edge_tuples = [(s, t, w) for s, t, _, w in all_edges]
                graph_scores = personalized_pagerank(edge_tuples, seed_weights)

        # State filter
        state_filter = {LifecycleState.ACTIVE, LifecycleState.DECIDED}
        if include_archived:
            state_filter.add(LifecycleState.ARCHIVED)

        # Score all candidates
        scored = self.scorer.score(
            candidates=candidates,
            fts_scores=fts_scores,
            vector_scores=vector_scores,
            graph_scores=graph_scores,
            state_filter=state_filter,
        )

        # Post-retrieval abstain check
        if scored and self.abstain_gate.should_abstain_post_retrieval(scored[0].total_score):
            return []

        return scored[:top_k]
