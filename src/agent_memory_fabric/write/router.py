"""Write Router — classifies incoming information into write operation types.

Hash dedup pattern adapted from Mem0 (Apache 2.0).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from agent_memory_fabric.core.node import LifecycleState, MemoryNode, WriteOperation

TTL_PATTERNS = re.compile(
    r"\b(expires?|deadline|due|until|by)\b.*\b(\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2})\b",
    re.IGNORECASE,
)


# Pattern from Mem0 (Apache 2.0) — hash dedup
def compute_hash(content: str) -> str:
    """MD5 hash of normalized content for deduplication."""
    normalized = content.strip().lower()
    return hashlib.md5(normalized.encode()).hexdigest()


def dedup_check(content: str, existing_hashes: set[str]) -> bool:
    """Returns True if content is a duplicate (should skip)."""
    return compute_hash(content) in existing_hashes


class WriteRouter:
    """Classifies incoming content into one of 6 write operations.

    Fast path (no LLM):
    1. Hash match → Skip (duplicate)
    2. TTL pattern detected → tag for expiration
    3. Default: Append

    LLM path (Phase 3): will handle Replace, Synthesize, Branch, Promote.
    """

    def classify(
        self,
        content: str,
        existing_node: MemoryNode | None = None,
        existing_hashes: set[str] | None = None,
    ) -> WriteOperation | None:
        """Classify the write operation. Returns None if content should be skipped (duplicate)."""
        if existing_hashes and dedup_check(content, existing_hashes):
            return None

        # LLM-based contradiction detection deferred to Phase 3.
        # For now, all non-duplicate content is classified as Append.
        return WriteOperation.APPEND

    def has_ttl_pattern(self, content: str) -> bool:
        """Check if content contains temporal expiration patterns."""
        return bool(TTL_PATTERNS.search(content))

    def execute(
        self,
        content: str,
        operation: WriteOperation,
        target_node: MemoryNode | None = None,
    ) -> MemoryNode | None:
        """Execute the classified write operation.

        Returns new/updated node, or None for skip.
        """
        now = datetime.now(timezone.utc)

        if operation == WriteOperation.APPEND:
            return MemoryNode(
                name=self._generate_name(content),
                content=content,
                state=LifecycleState.ACTIVE,
                created=now,
                modified=now,
                last_accessed=now,
            )

        if operation == WriteOperation.REPLACE and target_node:
            target_node.content = content
            target_node.modified = now
            return target_node

        if operation == WriteOperation.EXPIRE and target_node:
            target_node.state = LifecycleState.EXPIRED
            target_node.modified = now
            return target_node

        if operation == WriteOperation.SYNTHESIZE:
            return MemoryNode(
                name=f"synthesis-{now.strftime('%Y%m%d-%H%M%S')}",
                content=content,
                state=LifecycleState.DECIDED,
                created=now,
                modified=now,
                last_accessed=now,
            )

        return MemoryNode(
            name=self._generate_name(content),
            content=content,
            state=LifecycleState.ACTIVE,
            created=now,
            modified=now,
            last_accessed=now,
        )

    def _generate_name(self, content: str) -> str:
        words = content.split()[:5]
        name = "-".join(w.lower().strip(".,!?;:\"'()") for w in words if w)
        return name[:50] or "unnamed"
