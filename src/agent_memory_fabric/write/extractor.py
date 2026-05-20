"""Memory extraction — identifies what to remember from conversations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractionResult:
    content: str
    suggested_name: str
    suggested_tags: list[str]
    suggested_project: str | None
    confidence: float


class MemoryExtractor:
    """Extracts memory-worthy content from conversation turns.

    Inspired by Claude Code's forked-agent pattern:
    - Receives conversation context
    - Identifies facts, decisions, preferences worth persisting
    - Filters noise (greetings, confirmations, pure execution)
    """

    def extract(self, conversation_turn: str, context: str | None = None) -> list[ExtractionResult]:
        """Extract memory candidates from a conversation turn."""
        raise NotImplementedError("Phase 2: LLM-based extraction")
