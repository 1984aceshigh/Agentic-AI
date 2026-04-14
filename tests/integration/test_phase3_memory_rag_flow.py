from __future__ import annotations

from agent_platform.executors.base import ExecutorRegistry
from agent_platform.executors.memory_read import MemoryReadExecutor, MemoryWriteExecutor
from agent_platform.executors.rag_retrieve import RAGRetrieveExecutor
from agent_platform.integrations.memory_backends import InMemoryMemoryStore
from agent_platform.integrations.rag_backends import InMemoryVectorRetriever, load_document_chunks


def _make_spec() -> dict:
    return {
        "integrations": {
            "memory_profiles": {
                "default_memory": {
                    "backend": "in_memory",
                    "contract": "memory_store",
                }
            },
            "rag_profiles": {
                "default_rag": {
                    "backend": "in_memory",
                    "contract": "vector_retriever",
                }
            },
        }
    }


def _make_context() -> dict:
    return {
        "workflow_id": "workflow_alpha",
        "execution_id": "execution_001",
        "global_inputs": {
            "search_query": "onboarding automation",
        },
        "node_outputs": {},
    }


def test_phase3_memory_write_then_read_roundtrip() -> None:
    spec = _make_spec()
    context = _make_context()
    store = InMemoryMemoryStore()

    write_executor = MemoryWriteExecutor(
        stores_by_profile_name={"default_memory": store}
    )
    read_executor = MemoryReadExecutor(
        stores_by_profile_name={"default_memory": store}
    )

    write_node = {
        "id": "write_memory",
        "type": "memory_write",
        "config": {
            "memory_profile": "default_memory",
            "scope": "workflow",
            "tags": ["project_context", "approved"],
            "content_template": {
                "summary": "Project Alpha approved for pilot",
                "owner": "PMO",
            },
        },
    }
    write_result = write_executor.run(spec=spec, node=write_node, context=context)
    assert write_result.status == "SUCCEEDED"
    context["node_outputs"]["write_memory"] = write_result.output

    read_node = {
        "id": "read_memory",
        "type": "memory_read",
        "config": {
            "memory_profile": "default_memory",
            "scope": "workflow",
            "query": {
                "tags": ["project_context"],
                "limit": 5,
            },
        },
    }
    read_result = read_executor.run(spec=spec, node=read_node, context=context)

    assert read_result.status == "SUCCEEDED"
    assert read_result.output["count"] == 1
    assert read_result.output["records"][0]["content"] == {
        "summary": "Project Alpha approved for pilot",
        "owner": "PMO",
    }



def test_phase3_rag_retrieve_returns_hits() -> None:
    spec = _make_spec()
    context = _make_context()
    retriever = InMemoryVectorRetriever(
        chunks=load_document_chunks(
            [
                {
                    "chunk_id": "c1",
                    "document_id": "doc1",
                    "text": "Onboarding automation reduces manual work in operations.",
                    "metadata": {"topic": "operations"},
                },
                {
                    "chunk_id": "c2",
                    "document_id": "doc2",
                    "text": "Liquidity risk monitoring is important for banks.",
                    "metadata": {"topic": "risk"},
                },
                {
                    "chunk_id": "c3",
                    "document_id": "doc3",
                    "text": "Customer onboarding workflow design for digital channels.",
                    "metadata": {"topic": "onboarding"},
                },
            ]
        )
    )
    executor = RAGRetrieveExecutor(
        retrievers_by_profile_name={"default_rag": retriever}
    )

    node = {
        "id": "rag_lookup",
        "type": "rag_retrieve",
        "config": {
            "rag_profile": "default_rag",
            "query_text": "onboarding automation",
            "top_k": 2,
        },
    }
    result = executor.run(spec=spec, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output["count"] == 2
    assert result.output["query_text"] == "onboarding automation"
    assert result.output["hits"][0]["chunk_id"] in {"c1", "c3"}



def test_phase3_registry_runs_mixed_memory_and_rag_flow() -> None:
    spec = _make_spec()
    context = _make_context()
    store = InMemoryMemoryStore()
    retriever = InMemoryVectorRetriever(
        chunks=load_document_chunks(
            [
                {
                    "chunk_id": "c1",
                    "document_id": "doc1",
                    "text": "Project Alpha focuses on onboarding automation for SMEs.",
                    "metadata": {"topic": "alpha"},
                },
                {
                    "chunk_id": "c2",
                    "document_id": "doc2",
                    "text": "Treasury optimization and liquidity controls.",
                    "metadata": {"topic": "treasury"},
                },
            ]
        )
    )

    registry = ExecutorRegistry()
    registry.register_executor(
        MemoryWriteExecutor(stores_by_profile_name={"default_memory": store})
    )
    registry.register_executor(
        MemoryReadExecutor(stores_by_profile_name={"default_memory": store})
    )
    registry.register_executor(
        RAGRetrieveExecutor(retrievers_by_profile_name={"default_rag": retriever})
    )

    nodes = [
        {
            "id": "write_memory",
            "type": "memory_write",
            "config": {
                "memory_profile": "default_memory",
                "scope": "workflow",
                "tags": ["brief"],
                "content_template": {"summary": "Alpha project brief stored"},
            },
        },
        {
            "id": "read_memory",
            "type": "memory_read",
            "config": {
                "memory_profile": "default_memory",
                "scope": "workflow",
                "query": {"tags": ["brief"], "limit": 5},
            },
        },
        {
            "id": "rag_lookup",
            "type": "rag_retrieve",
            "config": {
                "rag_profile": "default_rag",
                "query_source": {"global_input": "search_query"},
                "top_k": 1,
            },
        },
    ]

    for node in nodes:
        executor = registry.resolve_for_node(node)
        result = executor.run(spec=spec, node=node, context=context)
        assert result.status == "SUCCEEDED"
        context["node_outputs"][node["id"]] = result.output

    assert "write_memory" in context["node_outputs"]
    assert "read_memory" in context["node_outputs"]
    assert "rag_lookup" in context["node_outputs"]
    assert context["node_outputs"]["read_memory"]["count"] == 1
    assert context["node_outputs"]["rag_lookup"]["count"] == 1
    assert context["node_outputs"]["rag_lookup"]["query_text"] == "onboarding automation"
