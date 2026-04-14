from dataclasses import dataclass, field
from typing import Any

from agent_platform.executors.rag_retrieve import RAGRetrieveExecutor
from agent_platform.integrations.rag_backends import InMemoryVectorRetriever
from agent_platform.integrations.rag_contracts import DocumentChunk


class StubProfileResolver:
    def __init__(self, *, allowed_profiles: set[str]) -> None:
        self.allowed_profiles = allowed_profiles

    def resolve_rag_profile(self, spec: Any, profile_name: str) -> dict[str, str]:
        if profile_name not in self.allowed_profiles:
            raise ValueError(f"unknown rag profile: {profile_name}")
        return {"name": profile_name}


@dataclass
class DummyContext:
    global_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class DummyNode:
    id: str
    type: str
    config: dict[str, Any]
    input: dict[str, Any] = field(default_factory=dict)



def make_executor() -> RAGRetrieveExecutor:
    retriever = InMemoryVectorRetriever(
        chunks=[
            DocumentChunk(chunk_id="c1", document_id="d1", text="loan underwriting workflow"),
            DocumentChunk(chunk_id="c2", document_id="d1", text="greenhouse tomato cultivation"),
            DocumentChunk(chunk_id="c3", document_id="d2", text="credit review memo"),
        ]
    )
    return RAGRetrieveExecutor(
        retrievers_by_profile_name={"default_rag": retriever},
        profile_resolver=StubProfileResolver(allowed_profiles={"default_rag"}),
    )



def test_rag_retrieve_executor_returns_hits_from_direct_query_text() -> None:
    executor = make_executor()
    node = DummyNode(
        id="retrieve_docs",
        type="rag_retrieve",
        config={
            "rag_profile": "default_rag",
            "query_text": "credit workflow",
            "top_k": 2,
        },
    )

    result = executor.run(spec={}, node=node, context=DummyContext())

    assert result.status == "SUCCEEDED"
    assert result.output["count"] == 2
    assert result.output["query_text"] == "credit workflow"
    assert result.output["hits"][0]["chunk_id"] in {"c1", "c3"}



def test_rag_retrieve_executor_builds_query_from_resolved_input() -> None:
    executor = make_executor()
    node = DummyNode(
        id="retrieve_docs",
        type="rag_retrieve",
        config={
            "rag_profile": "default_rag",
            "query_source": "question",
            "top_k": 1,
        },
        input={
            "from": [
                {"node": "planner", "key": "question", "as": "question"},
            ]
        },
    )
    context = DummyContext(node_outputs={"planner": {"question": "loan review"}})

    result = executor.run(spec={}, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output["count"] == 1
    assert result.output["query_text"] == "loan review"



def test_rag_retrieve_executor_fails_for_unknown_profile() -> None:
    executor = make_executor()
    node = DummyNode(
        id="retrieve_docs",
        type="rag_retrieve",
        config={
            "rag_profile": "unknown_profile",
            "query_text": "credit workflow",
        },
    )

    result = executor.run(spec={}, node=node, context=DummyContext())

    assert result.status == "FAILED"
    assert "unknown rag profile" in (result.error_message or "")



def test_rag_retrieve_executor_fails_for_empty_query() -> None:
    executor = make_executor()
    node = DummyNode(
        id="retrieve_docs",
        type="rag_retrieve",
        config={
            "rag_profile": "default_rag",
            "query_text": "   ",
        },
    )

    result = executor.run(spec={}, node=node, context=DummyContext())

    assert result.status == "FAILED"
    assert "query_text" in (result.error_message or "")
