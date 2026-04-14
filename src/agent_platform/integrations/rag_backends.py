from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from agent_platform.integrations.rag_contracts import (
    DocumentChunk,
    EmbeddingAdapter,
    RetrievalHit,
    RetrievalQuery,
    VectorRetriever,
)


class SimpleHashEmbeddingAdapter(EmbeddingAdapter):
    """Deterministic pseudo embedding for MVP tests and local development."""

    def __init__(self, *, vector_size: int = 32) -> None:
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")
        self._vector_size = vector_size

    def embed_text(self, text: str) -> list[float]:
        tokens = _tokenize(text)
        vector = [0.0] * self._vector_size
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._vector_size
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            magnitude = 1.0 + (digest[5] / 255.0)
            vector[index] += sign * magnitude

        return _normalize(vector)


class InMemoryVectorRetriever(VectorRetriever):
    """Simple in-memory retriever backed by deterministic embeddings."""

    def __init__(
        self,
        *,
        chunks: Sequence[DocumentChunk] | None = None,
        embedding_adapter: EmbeddingAdapter | None = None,
    ) -> None:
        self._embedding_adapter = embedding_adapter or SimpleHashEmbeddingAdapter()
        self._chunks: list[DocumentChunk] = []
        if chunks:
            self.extend(chunks)

    def extend(self, chunks: Sequence[DocumentChunk]) -> None:
        for chunk in chunks:
            embedding = chunk.embedding
            if embedding is None:
                embedding = self._embedding_adapter.embed_text(chunk.text)
            self._chunks.append(
                DocumentChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    metadata=dict(chunk.metadata),
                    embedding=list(embedding),
                )
            )

    @property
    def chunks(self) -> list[DocumentChunk]:
        return list(self._chunks)

    def retrieve(self, query: RetrievalQuery) -> list[RetrievalHit]:
        query_text = query.query_text.strip()
        if not query_text:
            return []

        query_embedding = self._embedding_adapter.embed_text(query_text)
        hits: list[RetrievalHit] = []
        for chunk in self._chunks:
            if not _metadata_matches(chunk.metadata, query.filters):
                continue
            chunk_embedding = chunk.embedding or self._embedding_adapter.embed_text(chunk.text)
            score = _cosine_similarity(query_embedding, chunk_embedding)
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    score=score,
                    metadata=dict(chunk.metadata),
                )
            )

        hits.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return hits[: max(query.top_k, 0)]


def load_document_chunks(items: Sequence[DocumentChunk | Mapping[str, Any]]) -> list[DocumentChunk]:
    loaded: list[DocumentChunk] = []
    for item in items:
        if isinstance(item, DocumentChunk):
            loaded.append(item)
        else:
            loaded.append(DocumentChunk.model_validate(item))
    return loaded


def _metadata_matches(metadata: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        if metadata.get(key) != expected:
            return False
    return True


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())



def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]



def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding size mismatch")
    return sum(a * b for a, b in zip(left, right))
