from __future__ import annotations

import pytest

from agent_platform.integrations.rag_contracts import (
    DocumentChunk,
    EmbeddingAdapter,
    RetrievalHit,
    RetrievalQuery,
    VectorRetriever,
)


class DummyEmbeddingAdapter(EmbeddingAdapter):
    def embed_text(self, text: str) -> list[float]:
        return [float(len(text))]


class DummyVectorRetriever(VectorRetriever):
    def retrieve(self, query: RetrievalQuery) -> list[RetrievalHit]:
        return [
            RetrievalHit(
                chunk_id="chunk-1",
                document_id="doc-1",
                text="matched text",
                score=0.95,
                metadata={"source": "unit-test"},
            )
        ]


def test_document_chunk_can_be_created() -> None:
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        text="hello",
        metadata={"section": "intro"},
        embedding=[0.1, 0.2],
    )

    assert chunk.chunk_id == "chunk-1"
    assert chunk.document_id == "doc-1"
    assert chunk.text == "hello"
    assert chunk.metadata == {"section": "intro"}
    assert chunk.embedding == [0.1, 0.2]


def test_document_chunk_defaults_are_applied() -> None:
    chunk = DocumentChunk(
        chunk_id="chunk-2",
        document_id="doc-2",
        text="body",
    )

    assert chunk.metadata == {}
    assert chunk.embedding is None


def test_retrieval_query_default_top_k_is_applied() -> None:
    query = RetrievalQuery(query_text="what is agentic ai?")

    assert query.query_text == "what is agentic ai?"
    assert query.top_k == 5
    assert query.filters == {}


def test_retrieval_query_can_accept_filters() -> None:
    query = RetrievalQuery(
        query_text="find documents",
        top_k=3,
        filters={"department": "research"},
    )

    assert query.top_k == 3
    assert query.filters == {"department": "research"}


def test_retrieval_hit_can_be_created() -> None:
    hit = RetrievalHit(
        chunk_id="chunk-3",
        document_id="doc-3",
        text="matched paragraph",
        score=0.87,
        metadata={"page": 2},
    )

    assert hit.chunk_id == "chunk-3"
    assert hit.document_id == "doc-3"
    assert hit.text == "matched paragraph"
    assert hit.score == pytest.approx(0.87)
    assert hit.metadata == {"page": 2}


def test_embedding_adapter_can_be_implemented() -> None:
    adapter = DummyEmbeddingAdapter()

    result = adapter.embed_text("abc")

    assert result == [3.0]


def test_vector_retriever_can_be_implemented() -> None:
    retriever = DummyVectorRetriever()

    result = retriever.retrieve(RetrievalQuery(query_text="test"))

    assert len(result) == 1
    assert result[0].chunk_id == "chunk-1"
    assert result[0].score == pytest.approx(0.95)


def test_embedding_adapter_is_abstract() -> None:
    with pytest.raises(TypeError):
        EmbeddingAdapter()


def test_vector_retriever_is_abstract() -> None:
    with pytest.raises(TypeError):
        VectorRetriever()
