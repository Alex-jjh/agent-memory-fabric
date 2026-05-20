"""AMF configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class DecayConfig(BaseModel):
    model: str = "ebbinghaus"  # ebbinghaus | power_law | exponential
    half_life_days: float = 14.0
    forget_threshold: float = 0.05
    promote_threshold: float = 0.65


class RetrieverConfig(BaseModel):
    top_k: int = 5
    hot_budget_tokens: int = 1300
    warm_budget_tokens: int = 2000
    gateway_timeout_ms: int = 100
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


class ScorerWeights(BaseModel):
    semantic: float = 0.40
    graph_proximity: float = 0.20
    recency: float = 0.25
    frequency: float = 0.15
    # Phase 3 signals (not yet wired into MultiSignalScorer):
    intent: float = 0.0
    hierarchy: float = 0.0


class AMFConfig(BaseModel):
    vault_path: Path = Field(default_factory=lambda: Path.home() / "memory-vault")
    db_path: Optional[Path] = None  # defaults to vault_path/.amf/index.db
    decay: DecayConfig = Field(default_factory=DecayConfig)
    retriever: RetrieverConfig = Field(default_factory=RetrieverConfig)
    scorer_weights: ScorerWeights = Field(default_factory=ScorerWeights)
    consolidation_interval_hours: float = 24.0
    transition_check_interval_minutes: float = 60.0

    def get_db_path(self) -> Path:
        if self.db_path:
            return self.db_path
        return self.vault_path / ".amf" / "index.db"
