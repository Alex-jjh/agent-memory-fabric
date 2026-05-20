"""Policy-based composition: pluggable extraction + consolidation per memory type."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from agent_memory_fabric.core.node import MemoryType


class Extractor(Protocol):
    """Interface for memory extraction strategies."""

    def extract(self, text: str, context: str | None = None) -> list[Any]: ...


class Consolidator(Protocol):
    """Interface for memory consolidation strategies."""

    def consolidate(self, new_content: str, existing_contents: list[str]) -> Any: ...


class MemoryPolicy(BaseModel):
    """Bundles an extraction + consolidation strategy for a memory type."""

    name: str
    memory_type: MemoryType
    confidence_floor: float = Field(default=0.3, ge=0.0, le=1.0)
    enabled: bool = True

    model_config = {"arbitrary_types_allowed": True}

    _extractor: Any = None
    _consolidator: Any = None

    def set_extractor(self, extractor: Extractor) -> None:
        self._extractor = extractor

    def set_consolidator(self, consolidator: Consolidator | None) -> None:
        self._consolidator = consolidator

    @property
    def extractor(self) -> Extractor | None:
        return self._extractor

    @property
    def consolidator(self) -> Consolidator | None:
        return self._consolidator


class PolicyRegistry:
    """Registry of memory policies, indexed by memory type."""

    def __init__(self):
        self._policies: dict[MemoryType, MemoryPolicy] = {}

    def register(self, policy: MemoryPolicy) -> None:
        self._policies[policy.memory_type] = policy

    def get(self, memory_type: MemoryType) -> MemoryPolicy | None:
        return self._policies.get(memory_type)

    def list_policies(self) -> list[MemoryPolicy]:
        return list(self._policies.values())

    def list_enabled(self) -> list[MemoryPolicy]:
        return [p for p in self._policies.values() if p.enabled]

    @property
    def count(self) -> int:
        return len(self._policies)
