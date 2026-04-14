from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None


class RetrievalQuery(BaseModel):
    query_text: str
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class RetrievalHit(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingAdapter(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError


class VectorRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: RetrievalQuery) -> list[RetrievalHit]:
        raise NotImplementedError
