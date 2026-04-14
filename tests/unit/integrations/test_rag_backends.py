from agent_platform.integrations.rag_backends import (
    InMemoryVectorRetriever,
    SimpleHashEmbeddingAdapter,
    load_document_chunks,
)
from agent_platform.integrations.rag_contracts import DocumentChunk, RetrievalQuery



def test_embedding_is_deterministic() -> None:
    adapter = SimpleHashEmbeddingAdapter(vector_size=16)

    first = adapter.embed_text("bank lending workflow")
    second = adapter.embed_text("bank lending workflow")

    assert first == second
    assert len(first) == 16



def test_load_document_chunks_accepts_dicts_and_models() -> None:
    chunks = load_document_chunks(
        [
            {"chunk_id": "c1", "document_id": "d1", "text": "alpha"},
            DocumentChunk(chunk_id="c2", document_id="d1", text="beta"),
        ]
    )

    assert len(chunks) == 2
    assert chunks[0].chunk_id == "c1"
    assert chunks[1].chunk_id == "c2"



def test_retriever_returns_top_k_and_relevant_chunk_first() -> None:
    retriever = InMemoryVectorRetriever(
        chunks=[
            DocumentChunk(chunk_id="c1", document_id="d1", text="loan underwriting workflow"),
            DocumentChunk(chunk_id="c2", document_id="d1", text="tomato greenhouse cultivation"),
            DocumentChunk(chunk_id="c3", document_id="d2", text="corporate lending credit review"),
        ]
    )

    hits = retriever.retrieve(RetrievalQuery(query_text="lending credit workflow", top_k=2))

    assert len(hits) == 2
    assert hits[0].chunk_id in {"c1", "c3"}
    assert hits[0].score >= hits[1].score



def test_retriever_is_deterministic() -> None:
    retriever = InMemoryVectorRetriever(
        chunks=[
            DocumentChunk(chunk_id="c1", document_id="d1", text="risk management controls"),
            DocumentChunk(chunk_id="c2", document_id="d1", text="project governance review"),
        ]
    )
    query = RetrievalQuery(query_text="risk control review", top_k=2)

    first = retriever.retrieve(query)
    second = retriever.retrieve(query)

    assert [hit.model_dump() for hit in first] == [hit.model_dump() for hit in second]



def test_retriever_applies_metadata_filters() -> None:
    retriever = InMemoryVectorRetriever(
        chunks=[
            DocumentChunk(
                chunk_id="c1",
                document_id="d1",
                text="risk management controls",
                metadata={"category": "risk"},
            ),
            DocumentChunk(
                chunk_id="c2",
                document_id="d1",
                text="project governance review",
                metadata={"category": "pm"},
            ),
        ]
    )

    hits = retriever.retrieve(
        RetrievalQuery(query_text="review", top_k=5, filters={"category": "pm"})
    )

    assert len(hits) == 1
    assert hits[0].chunk_id == "c2"
