"""Short-query context expansion: improve retrieval for terse queries."""

from __future__ import annotations

SHORT_QUERY_WORD_THRESHOLD = 3
PRIOR_CONTEXT_WORDS = 7


class QueryExpander:
    """Expands short queries with prior turn context for better retrieval.

    When a user query has ≤ 3 words (e.g., "what about that?"), the embedding
    and FTS search may fail to find relevant memories. By appending context from
    the prior turn, we give the retrieval system more signal.
    """

    def __init__(
        self,
        threshold: int = SHORT_QUERY_WORD_THRESHOLD,
        context_words: int = PRIOR_CONTEXT_WORDS,
    ):
        self.threshold = threshold
        self.context_words = context_words
        self._prior_user: str | None = None
        self._prior_assistant: str | None = None

    def expand(self, query: str) -> str:
        """If query is short, append prior turn context."""
        words = query.split()
        if len(words) > self.threshold:
            return query

        context_parts: list[str] = []
        if self._prior_user:
            context_parts.append(self._extract_context(self._prior_user))
        if self._prior_assistant:
            context_parts.append(self._extract_context(self._prior_assistant))

        if not context_parts:
            return query

        context = " ".join(context_parts)
        return f"{query} {context}"

    def record_turn(self, role: str, message: str) -> None:
        """Track recent messages for context expansion."""
        if role in ("user", "human"):
            self._prior_user = message
        elif role in ("assistant", "ai"):
            self._prior_assistant = message

    def reset(self) -> None:
        """Reset state for new conversation/session."""
        self._prior_user = None
        self._prior_assistant = None

    def _extract_context(self, text: str) -> str:
        """First N words + last N words of text."""
        words = text.split()
        if len(words) <= self.context_words * 2:
            return text
        first = words[:self.context_words]
        last = words[-self.context_words:]
        return " ".join(first) + " ... " + " ".join(last)
