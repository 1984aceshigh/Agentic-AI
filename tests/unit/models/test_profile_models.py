from __future__ import annotations

from agent_platform.models import ContractType, LLMProfile, MemoryProfile, NodeType, RAGProfile


def test_llm_profile_can_be_created() -> None:
    profile = LLMProfile(provider="openai", model="gpt-5.4", temperature=0.2, max_tokens=2048)
    assert profile.provider == "openai"
    assert profile.model == "gpt-5.4"


def test_memory_profile_can_be_created() -> None:
    profile = MemoryProfile(backend="sqlite", namespace="default")
    assert profile.backend == "sqlite"
    assert profile.namespace == "default"


def test_rag_profile_can_be_created() -> None:
    profile = RAGProfile(
        backend="pgvector",
        collection="knowledge_base",
        embedding_model="text-embedding-3-large",
    )
    assert profile.collection == "knowledge_base"
    assert profile.top_k == 5


def test_contract_type_enum_values_match_expected_spec() -> None:
    assert [item.value for item in ContractType] == [
        "llm_completion",
        "memory_store",
        "vector_retriever",
        "tool_invocation",
        "file_access",
    ]


def test_node_type_enum_values_match_expected_spec() -> None:
    assert [item.value for item in NodeType] == [
        "llm",
        "human_gate",
        "api",
        "mcp",
    ]
