"""MemoryNode — the fundamental unit of memory in AMF."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LifecycleState(str, Enum):
    ACTIVE = "active"
    DECIDED = "decided"
    ARCHIVED = "archived"
    EXPIRED = "expired"


class MemoryType(str, Enum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"
    ENTITY = "entity"


class WriteOperation(str, Enum):
    REPLACE = "replace"
    APPEND = "append"
    SYNTHESIZE = "synthesize"
    EXPIRE = "expire"
    BRANCH = "branch"
    PROMOTE = "promote"


class MemoryNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    content: str
    state: LifecycleState = LifecycleState.ACTIVE
    type: MemoryType = MemoryType.PROJECT
    project: Optional[str] = None
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    decay_score: float = 1.0
    strength: float = 1.0
    confidence_alpha: float = 1.0
    confidence_beta: float = 1.0
    ttl: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    applicable_domains: list[str] = Field(default_factory=list)
    recent_outcomes: list[dict] = Field(default_factory=list)
    is_anti_pattern: bool = False
    superseded_by: str | None = None

    def is_retrievable(self, include_archived: bool = False) -> bool:
        if self.state == LifecycleState.EXPIRED:
            return False
        if self.state == LifecycleState.ARCHIVED and not include_archived:
            return False
        return True

    def touch(self) -> None:
        self.last_accessed = datetime.now(timezone.utc)
        self.access_count += 1
