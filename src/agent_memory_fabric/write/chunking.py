"""Windowed chunking: process long conversations in manageable segments with past context."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversationChunk:
    """A segment of conversation for extraction."""
    current_turns: list[str]
    past_turns: list[str] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0


class WindowedChunker:
    """Splits conversations into overlapping windows for extraction.

    Each chunk contains:
    - current_turns: the turns to extract from (turn_size)
    - past_turns: preceding context for disambiguation (past_turn_size)

    Citation filtering ensures only facts from current_turns are kept,
    preventing re-extraction of previously processed information.
    """

    def __init__(self, turn_size: int = 12, past_turn_size: int = 4):
        self.turn_size = turn_size
        self.past_turn_size = past_turn_size

    def chunk_conversation(self, turns: list[str]) -> list[ConversationChunk]:
        """Split turns into chunks with past context windows."""
        if not turns:
            return []

        if len(turns) <= self.turn_size:
            return [ConversationChunk(
                current_turns=turns,
                past_turns=[],
                start_index=0,
                end_index=len(turns) - 1,
            )]

        chunks: list[ConversationChunk] = []
        for i in range(0, len(turns), self.turn_size):
            current = turns[i:i + self.turn_size]
            past_start = max(0, i - self.past_turn_size)
            past = turns[past_start:i] if past_start < i else []

            chunks.append(ConversationChunk(
                current_turns=current,
                past_turns=past,
                start_index=i,
                end_index=min(i + len(current) - 1, len(turns) - 1),
            ))

        return chunks

    def filter_citations(
        self,
        extracted_contents: list[str],
        current_turns: list[str],
    ) -> list[str]:
        """Keep only extractions grounded in the current chunk, not past context.

        An extraction is considered grounded if at least one significant word
        from it appears in the current turns.
        """
        if not current_turns:
            return []

        current_text_lower = " ".join(current_turns).lower()
        current_words = set(current_text_lower.split())

        filtered: list[str] = []
        for content in extracted_contents:
            content_words = set(content.lower().split())
            significant = {w for w in content_words if len(w) > 2}
            if not significant:
                filtered.append(content)
                continue
            overlap = significant & current_words
            if overlap:
                filtered.append(content)

        return filtered
