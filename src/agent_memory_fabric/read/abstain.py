"""Abstain Gate — decides whether a turn needs memory injection at all.

Research (TARG) shows 70-90% of turns don't benefit from injection.
This gate prevents unnecessary retrieval and context bloat.
"""

from __future__ import annotations

import re

GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|good morning|good evening|good night|thanks|thank you|"
    r"ok|okay|sure|got it|alright|bye|goodbye|see you|cheers|yo|sup)\b",
    re.IGNORECASE,
)

CONFIRMATION_PATTERNS = re.compile(
    r"^(yes|no|yeah|yep|nope|nah|correct|right|exactly|indeed|absolutely)\b",
    re.IGNORECASE,
)


class AbstainGate:
    """Decides whether to skip memory retrieval for a given message.

    Heuristics:
    1. Very short messages (< min_words) → abstain
    2. Pure greetings/confirmations → abstain
    3. Best retrieval score below threshold → abstain (post-retrieval check)
    """

    def __init__(
        self,
        min_words: int = 3,
        score_threshold: float = 0.15,
    ):
        self.min_words = min_words
        self.score_threshold = score_threshold

    def should_abstain(self, message: str) -> bool:
        """Pre-retrieval check: should we skip retrieval entirely?"""
        stripped = message.strip()
        if not stripped:
            return True

        words = stripped.split()
        if len(words) < self.min_words:
            return True

        if GREETING_PATTERNS.match(stripped):
            return True

        if CONFIRMATION_PATTERNS.match(stripped):
            return True

        return False

    def should_abstain_post_retrieval(self, best_score: float) -> bool:
        """Post-retrieval check: are the results worth injecting?"""
        return best_score < self.score_threshold
