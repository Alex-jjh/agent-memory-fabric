"""Memory extraction — identifies what to remember from conversations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_memory_fabric.llm.provider import LLMProvider


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


_LLM_EXTRACTION_SYSTEM = """You are a memory extraction agent. Extract discrete, standalone facts from the conversation.

Output a JSON array of objects, each with:
- "content": the fact as a standalone sentence (no pronouns, include context)
- "tags": list of relevant tags
- "confidence": 0.0-1.0 how certain this is a lasting fact (not ephemeral)

Only extract facts worth remembering long-term: preferences, decisions, personal info, project details, procedures.
Do NOT extract: greetings, confirmations, questions, ephemeral status updates."""

_LLM_EXTRACTION_USER = """Extract memories from this conversation segment:

<context>
{context}
</context>

<current>
{content}
</current>

Only extract facts from <current>, using <context> for disambiguation only.
Output JSON array:"""

_GLEANING_PROMPT = """Review the facts you just extracted. Did you miss any important information?
Look specifically for: preferences, decisions, relationships, deadlines, project structure.
Output additional facts as a JSON array (empty array [] if nothing was missed):"""


class LLMExtractor:
    """LLM-based memory extraction with multi-pass gleaning."""

    def __init__(self, provider: "LLMProvider", max_gleaning_passes: int = 1):
        self.provider = provider
        self.max_gleaning_passes = max_gleaning_passes

    def extract(self, text: str, context: str | None = None) -> list[ExtractionResult]:
        """Extract memories using LLM with optional gleaning pass."""
        user_prompt = _LLM_EXTRACTION_USER.format(
            context=context or "(no prior context)",
            content=text,
        )

        try:
            response = self.provider.complete(_LLM_EXTRACTION_SYSTEM, user_prompt)
            results = self._parse_response(response)
        except Exception:
            return []

        for _ in range(self.max_gleaning_passes):
            if not results:
                break
            try:
                gleaning_response = self.provider.complete(
                    _LLM_EXTRACTION_SYSTEM,
                    user_prompt + "\n\n" + response + "\n\n" + _GLEANING_PROMPT,
                )
                additional = self._parse_response(gleaning_response)
                if not additional:
                    break
                results.extend(additional)
                response += "\n" + gleaning_response
            except Exception:
                break

        return results

    def _parse_response(self, response: str) -> list[ExtractionResult]:
        """Parse LLM JSON response into ExtractionResults."""
        response = response.strip()
        start = response.find("[")
        end = response.rfind("]")
        if start == -1 or end == -1:
            return []

        try:
            items = json.loads(response[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return []

        results: list[ExtractionResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = item.get("content", "").strip()
            if not content or len(content.split()) < 3:
                continue
            results.append(ExtractionResult(
                content=content,
                suggested_name=generate_name(content),
                suggested_tags=item.get("tags", []),
                confidence=min(1.0, max(0.0, float(item.get("confidence", 0.5)))),
            ))

        return results
