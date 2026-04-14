from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryScope(str, Enum):
    """Logical scope for persisted memory records."""

    EXECUTION = "execution"
    WORKFLOW = "workflow"
    SHARED = "shared"


class MemoryRecord(BaseModel):
    """A stored memory record independent from any concrete backend."""

    record_id: str
    scope: MemoryScope
    workflow_id: str | None = None
    execution_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime | None = None


class MemoryQuery(BaseModel):
    """Read query for memory retrieval."""

    scope: MemoryScope | None = None
    workflow_id: str | None = None
    execution_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = 5


class MemoryWriteRequest(BaseModel):
    """Write request for memory persistence."""

    scope: MemoryScope
    workflow_id: str | None = None
    execution_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    content: dict[str, Any]


class MemoryStore(ABC):
    """Abstract memory backend contract."""

    @abstractmethod
    def read(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Return memory records matching the given query."""

    @abstractmethod
    def write(self, request: MemoryWriteRequest) -> MemoryRecord:
        """Persist a memory record and return the stored representation."""
