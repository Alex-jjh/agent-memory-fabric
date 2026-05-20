"""Memory extraction — identifies what to remember from conversations.

Rule-based V1 for testing. LLM-based extraction is Phase 3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    content: str
    suggested_name: str
    suggested_tags: list[str] = field(default_factory=list)
    suggested_project: str | None = None
    confidence: float = 0.5


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
NOISE_PATTERNS = re.compile(
    r"^(ok|okay|sure|thanks|thank you|yes|no|got it|i see|hmm|alright|right)\b",
    re.IGNORECASE,
)


def generate_name(content: str) -> str:
    """Generate a kebab-case name from the first 5 words of content."""
    words = content.split()[:5]
    parts = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in words]
    name = "-".join(p for p in parts if p)
    return name[:50] or "unnamed"


def suggest_tags(content: str) -> list[str]:
    """Simple keyword-based tag suggestion."""
    tags = []
    lower = content.lower()
    if any(w in lower for w in ("prefer", "like", "want", "always", "never")):
        tags.append("preference")
    if any(w in lower for w in ("decide", "decision", "chose", "confirmed")):
        tags.append("decision")
    if any(w in lower for w in ("learn", "found", "discovered", "realized")):
        tags.append("insight")
    if any(w in lower for w in ("todo", "task", "need to", "should", "must")):
        tags.append("action")
    if any(w in lower for w in ("meeting", "deadline", "date", "schedule")):
        tags.append("temporal")
    return tags


class MemoryExtractor:
    """Extracts memory-worthy content from conversation turns.

    V1: Rule-based sentence splitting + filtering.
    V2 (Phase 3): LLM-based extraction with prompts.
    """

    def __init__(self, min_words: int = 5, min_confidence: float = 0.3):
        self.min_words = min_words
        self.min_confidence = min_confidence

    def extract(self, text: str, context: str | None = None) -> list[ExtractionResult]:
        """Extract memory candidates from text.

        Args:
            text: The conversation turn or text to extract from.
            context: Optional surrounding context for better extraction.

        Returns:
            List of ExtractionResult candidates, filtered by quality.
        """
        sentences = self._split_sentences(text)
        results = []

        for sentence in sentences:
            if not self._is_extractable(sentence):
                continue

            confidence = self._estimate_confidence(sentence)
            if confidence < self.min_confidence:
                continue

            results.append(ExtractionResult(
                content=sentence,
                suggested_name=generate_name(sentence),
                suggested_tags=suggest_tags(sentence),
                confidence=confidence,
            ))

        return results

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences, handling common edge cases."""
        raw = SENTENCE_SPLIT.split(text.strip())
        sentences = []
        for s in raw:
            s = s.strip()
            if s:
                for line in s.split("\n"):
                    line = line.strip().lstrip("- •*>")
                    if line:
                        sentences.append(line)
        return sentences

    def _is_extractable(self, sentence: str) -> bool:
        """Filter out noise: too short, generic responses, or pure questions."""
        words = sentence.split()
        if len(words) < self.min_words:
            return False
        if NOISE_PATTERNS.match(sentence):
            return False
        if sentence.strip().endswith("?") and len(words) < 8:
            return False
        return True

    def _estimate_confidence(self, sentence: str) -> float:
        """Heuristic confidence based on sentence characteristics."""
        confidence = 0.5
        lower = sentence.lower()

        if any(w in lower for w in ("always", "never", "remember", "important")):
            confidence += 0.2
        if any(w in lower for w in ("i think", "maybe", "probably", "might")):
            confidence -= 0.1
        if any(w in lower for w in ("decided", "confirmed", "we agreed")):
            confidence += 0.2
        if len(sentence.split()) > 15:
            confidence += 0.1

        return max(0.0, min(1.0, confidence))
