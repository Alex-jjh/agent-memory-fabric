"""MemoryEngine — main entry point for AMF operations."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent_memory_fabric.core.config import AMFConfig
from agent_memory_fabric.core.node import LifecycleState, MemoryNode, MemoryType, WriteOperation
from agent_memory_fabric.lifecycle.state_machine import StateMachine
from agent_memory_fabric.lifecycle.transitions import (
    InactivityArchivePredicate,
    PromotionPredicate,
    TemporalDecayPredicate,
    TTLExpirationPredicate,
)
from agent_memory_fabric.lifecycle.confidence import BetaConfidence
from agent_memory_fabric.llm.contradiction import detect_contradictions
from agent_memory_fabric.llm.provider import LLMProvider
from agent_memory_fabric.read.embeddings import EmbeddingProvider
from agent_memory_fabric.read.gateway import ProactiveGateway
from agent_memory_fabric.read.scorer import MultiSignalScorer, ScoredMemory
from agent_memory_fabric.storage.graph import build_edges_from_wikilinks
from agent_memory_fabric.storage.markdown import MarkdownStore
from agent_memory_fabric.storage.sqlite_store import SQLiteStore
from agent_memory_fabric.write.extractor import generate_name
from agent_memory_fabric.write.router import WriteRouter, compute_hash


class MemoryEngine:
    """Central coordinator for all AMF operations."""

    def __init__(self, vault_path: str | Path | None = None, config: AMFConfig | None = None):
        self.config = config or AMFConfig()
        if vault_path:
            self.config.vault_path = Path(vault_path)

        self.markdown_store = MarkdownStore(self.config.vault_path)
        self.sqlite_store = SQLiteStore(self.config.get_db_path())
        self.state_machine = StateMachine(self.config.decay)
        self.write_router = WriteRouter()
        self.scorer = MultiSignalScorer(self.config.scorer_weights, decay_config=self.config.decay)
        self._predicates = [
            TTLExpirationPredicate(),
            PromotionPredicate(
                score_threshold=self.config.decay.promote_threshold,
            ),
            TemporalDecayPredicate(
                decay_threshold=self.config.decay.forget_threshold,
                min_inactive_days=14,
            ),
            InactivityArchivePredicate(inactive_days=30),
        ]
        self._content_hashes: set[str] = set()
        self._lock = threading.Lock()

        self._initialize()

    def _initialize(self) -> None:
        self.markdown_store._ensure_dirs()
        self.sqlite_store.initialize()
        self._reconcile()

    def _reconcile(self) -> None:
        fs_nodes = self.markdown_store.list_all()
        self.sqlite_store.reconcile(fs_nodes)
        self._rebuild_edges(fs_nodes)
        self._content_hashes = {compute_hash(n.content) for n in fs_nodes}

    def _rebuild_edges(self, nodes: list[MemoryNode]) -> None:
        name_to_id = {n.name: n.id for n in nodes}
        for node in nodes:
            edges = build_edges_from_wikilinks(node.id, node.content, name_to_id)
            for source, target, edge_type, weight in edges:
                self.sqlite_store.add_edge(source, target, edge_type, weight)

    def write(
        self,
        content: str,
        operation: WriteOperation | str | None = None,
        project: str | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
        node_type: MemoryType | str = MemoryType.PROJECT,
        state: LifecycleState = LifecycleState.ACTIVE,
        ttl: datetime | None = None,
        strength: float = 1.0,
    ) -> Optional[MemoryNode]:
        """Create and persist a new memory node. Returns None if content is a duplicate."""
        with self._lock:
            return self._write_inner(content, operation, project, name, tags, node_type, state, ttl, strength)

    def _write_inner(
        self,
        content: str,
        operation: WriteOperation | str | None,
        project: str | None,
        name: str | None,
        tags: list[str] | None,
        node_type: MemoryType | str,
        state: LifecycleState,
        ttl: datetime | None,
        strength: float,
    ) -> Optional[MemoryNode]:
        # Fast-path dedup via WriteRouter
        op = self.write_router.classify(content, existing_hashes=self._content_hashes)
        if op is None:
            return None

        if operation:
            op = WriteOperation(operation) if isinstance(operation, str) else operation

        if name is None:
            name = generate_name(content)

        if isinstance(node_type, str):
            node_type = MemoryType(node_type)

        now = datetime.now(timezone.utc)
        node = MemoryNode(
            name=name,
            content=content,
            state=state,
            type=node_type,
            project=project,
            created=now,
            modified=now,
            last_accessed=now,
            tags=tags or [],
            ttl=ttl,
            strength=strength,
        )

        self.markdown_store.write(node)
        self.sqlite_store.upsert_node(node, content=content)
        self._content_hashes.add(compute_hash(content))

        all_nodes = self.sqlite_store.get_all_nodes()
        name_to_id = {r["name"]: r["id"] for r in all_nodes}
        edges = build_edges_from_wikilinks(node.id, content, name_to_id)
        for source, target, edge_type, weight in edges:
            self.sqlite_store.add_edge(source, target, edge_type, weight)

        return node

    def read(self, node_id: str) -> Optional[MemoryNode]:
        """Read a memory node by ID."""
        return self.markdown_store.read(node_id)

    def list_nodes(
        self,
        scope: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        """List node metadata from the index, optionally filtered."""
        return self.sqlite_store.get_all_nodes(state=state, project=scope)

    def transition(
        self,
        node_id: str,
        target_state: LifecycleState | str,
        reason: str | None = None,
    ) -> MemoryNode:
        """Manually trigger a state transition."""
        with self._lock:
            return self._transition_inner(node_id, target_state, reason)

    def _transition_inner(self, node_id: str, target_state: LifecycleState | str, reason: str | None) -> MemoryNode:
        node = self.markdown_store.read(node_id)
        if node is None:
            raise ValueError(f"Node not found: {node_id}")

        if isinstance(target_state, str):
            target_state = LifecycleState(target_state)

        self.state_machine.transition(node, target_state)
        node.modified = datetime.now(timezone.utc)
        self.markdown_store.write(node)
        self.sqlite_store.upsert_node(node, content=node.content)
        return node

    def run_transitions(self) -> list[tuple[str, LifecycleState, LifecycleState]]:
        """Evaluate all transition predicates on active nodes. Returns transitions fired."""
        transitions_fired: list[tuple[str, LifecycleState, LifecycleState]] = []
        active_nodes = self.sqlite_store.get_all_nodes(state="active")
        decided_nodes = self.sqlite_store.get_all_nodes(state="decided")

        from agent_memory_fabric.lifecycle.transitions import TemporalDecayPredicate

        for row in active_nodes + decided_nodes:
            node = self.markdown_store.read(row["id"])
            if node is None:
                continue

            confidence = node.confidence_alpha / (node.confidence_alpha + node.confidence_beta)

            for predicate in self._predicates:
                if isinstance(predicate, TemporalDecayPredicate):
                    target = predicate.evaluate(node, confidence=confidence)
                else:
                    target = predicate.evaluate(node)
                if target is not None and self.state_machine.can_transition(node, target):
                    old_state = node.state
                    self.state_machine.transition(node, target)
                    node.modified = datetime.now(timezone.utc)
                    self.markdown_store.write(node)
                    self.sqlite_store.upsert_node(node, content=node.content)
                    transitions_fired.append((node.id, old_state, target))
                    break

        return transitions_fired

    def detect_and_archive_contradictions(
        self,
        new_content: str,
        provider: LLMProvider,
        scope: str | None = None,
    ) -> list[tuple[str, str]]:
        """Detect memories contradicted by new content and archive them.

        Returns list of (node_id, reason) for each archived node.
        """
        all_nodes = self.markdown_store.list_all(scope=scope)
        active_nodes = [n for n in all_nodes if n.state == LifecycleState.ACTIVE]

        contradictions = detect_contradictions(new_content, active_nodes, provider)
        archived: list[tuple[str, str]] = []

        for node, reason in contradictions:
            if self.state_machine.can_transition(node, LifecycleState.ARCHIVED):
                self.state_machine.transition(node, LifecycleState.ARCHIVED)
                node.modified = datetime.now(timezone.utc)
                self.markdown_store.write(node)
                self.sqlite_store.upsert_node(node, content=node.content)
                archived.append((node.id, reason))

        return archived

    def run_trim(self, max_count: int | None = None) -> int:
        """Trim lowest-value memories if corpus exceeds capacity. Returns count trimmed."""
        from agent_memory_fabric.lifecycle.trim import AutoTrimmer

        trimmer = AutoTrimmer(max_count=max_count or 10000)
        active = self.list_nodes(state="active")
        decided = self.list_nodes(state="decided")
        total = len(active) + len(decided)
        if not trimmer.needs_trim(total):
            return 0

        nodes = [n for n in self.markdown_store.list_all() if n.state in (LifecycleState.ACTIVE, LifecycleState.DECIDED)]
        to_trim = trimmer.select_for_trim(nodes)
        return trimmer.execute_trim(self, to_trim)

    def run_consolidation(self) -> int:
        """Merge duplicates and synthesize insights. Returns count of nodes affected."""
        raise NotImplementedError("Phase 4: consolidation engine")

    def retrieve_proactive(
        self,
        message: str,
        scope: str | None = None,
        top_k: int | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> list[ScoredMemory]:
        """Proactive retrieval: select relevant memories for an incoming message.

        Uses the full pipeline: abstain gate → multi-signal scoring → tier assignment.
        Returns empty list if abstain gate fires.
        """
        gateway = ProactiveGateway(
            sqlite_store=self.sqlite_store,
            scorer=self.scorer,
            config=self.config.retriever,
            embedding_provider=embedding_provider,
        )

        all_nodes = self.markdown_store.list_all()
        return gateway.retrieve(message, all_nodes, scope=scope, top_k=top_k)

    def update_confidence(
        self, node_id: str, success: bool, weight: float = 1.0
    ) -> Optional[MemoryNode]:
        """Record a confidence outcome for a memory node.

        Updates alpha/beta on the node (persisted in frontmatter).
        If confidence drops below threshold, may trigger accelerated state transition.
        Returns updated node, or None if not found.
        """
        node = self.markdown_store.read(node_id)
        if node is None:
            return None

        conf = BetaConfidence(
            alpha=node.confidence_alpha,
            beta_param=node.confidence_beta,
            recent_outcomes=list(node.recent_outcomes),
            is_anti_pattern=node.is_anti_pattern,
        )
        conf.record_outcome(success=success, weight=weight)

        node.confidence_alpha = conf.alpha
        node.confidence_beta = conf.beta_param
        node.recent_outcomes = conf.recent_outcomes

        effective = conf.effective_confidence()

        if effective < 0.3:
            target = TemporalDecayPredicate(
                decay_threshold=self.config.decay.forget_threshold,
                min_inactive_days=7,
            ).evaluate(node, confidence=effective)
            if target and self.state_machine.can_transition(node, target):
                self.state_machine.transition(node, target)
                node.modified = datetime.now(timezone.utc)

        self.markdown_store.write(node)
        self.sqlite_store.upsert_node(node, content=node.content)
        return node

    def search(
        self,
        query: str,
        top_k: int = 5,
        scope: str | None = None,
        include_archived: bool = False,
    ) -> list[MemoryNode]:
        """Search memories using multi-signal scoring (BM25 + recency + frequency)."""
        fts_results = self.sqlite_store.search_fts(query, limit=top_k * 5)

        fts_node_ids = {node_id for node_id, _ in fts_results}
        fts_scores = {node_id: score for node_id, score in fts_results}

        candidates: list[MemoryNode] = []
        for node_id in fts_node_ids:
            node = self.markdown_store.read(node_id)
            if node is None:
                continue
            if scope and node.project != scope:
                continue
            candidates.append(node)

        state_filter = {LifecycleState.ACTIVE, LifecycleState.DECIDED}
        if include_archived:
            state_filter.add(LifecycleState.ARCHIVED)

        scored = self.scorer.score(
            candidates=candidates,
            fts_scores=fts_scores,
            state_filter=state_filter,
        )

        results: list[MemoryNode] = []
        for sm in scored[:top_k]:
            sm.node.touch()
            self.markdown_store.write(sm.node)
            self.sqlite_store.upsert_node(sm.node, content=sm.node.content)
            results.append(sm.node)

        return results
