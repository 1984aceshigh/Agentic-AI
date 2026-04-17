from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_platform.integrations.profile_resolver import (
    ProfileResolutionError,
    ProfileResolver,
)


@pytest.fixture
def resolver() -> ProfileResolver:
    return ProfileResolver()


@pytest.fixture
def workflow_spec() -> SimpleNamespace:
    return SimpleNamespace(
        integrations=SimpleNamespace(
            llm_profiles={
                "default_llm": SimpleNamespace(
                    provider="openai",
                    model="gpt-5.4",
                    contract="llm_completion",
                ),
            },
            memory_profiles={
                "default_memory": SimpleNamespace(
                    backend="sqlite",
                    namespace="default",
                    contract="memory_store",
                ),
            },
            rag_profiles={
                "default_rag": SimpleNamespace(
                    backend="pgvector",
                    collection="knowledge_base",
                    contract="vector_retriever",
                ),
            },
            tool_profiles={
                "corp_tools": SimpleNamespace(
                    adapter_ref="corp_mcp_tool_adapter",
                    contract="tool_invocation",
                ),
                "local_files": SimpleNamespace(
                    adapter_ref="local_file_adapter",
                    contract="file_access",
                ),
            },
        ),
    )


def make_node(node_type: str, config: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(id=f"{node_type}_node", type=node_type, config=config)


def test_resolve_llm_profile_returns_profile(
    resolver: ProfileResolver,
    workflow_spec: SimpleNamespace,
) -> None:
    profile = resolver.resolve_llm_profile(workflow_spec, "default_llm")

    assert profile.model == "gpt-5.4"
    assert profile.contract == "llm_completion"


@pytest.mark.parametrize(
    ("method_name", "profile_name"),
    [
        ("resolve_llm_profile", "missing_llm"),
        ("resolve_memory_profile", "missing_memory"),
        ("resolve_rag_profile", "missing_rag"),
        ("resolve_tool_profile", "missing_tool"),
    ],
)
def test_unknown_profile_raises_error(
    resolver: ProfileResolver,
    workflow_spec: SimpleNamespace,
    method_name: str,
    profile_name: str,
) -> None:
    method = getattr(resolver, method_name)

    with pytest.raises(ProfileResolutionError):
        method(workflow_spec, profile_name)


@pytest.mark.parametrize(
    ("node_type", "config", "expected_contract"),
    [
        ("llm", {"llm_profile": "default_llm"}, "llm_completion"),
        (
            "llm",
            {
                "llm_profile": "default_llm",
                "memory": {"read": {"profile": "default_memory"}},
            },
            "llm_completion",
        ),
        (
            "llm",
            {
                "llm_profile": "default_llm",
                "memory": {"write": {"profile": "default_memory"}},
            },
            "llm_completion",
        ),
        (
            "llm",
            {
                "llm_profile": "default_llm",
                "rag": {"profile": "default_rag"},
            },
            "llm_completion",
        ),
        ("api", {"tool_profile": "corp_tools"}, "tool_invocation"),
        ("api", {"tool_profile": "local_files"}, "file_access"),
        ("mcp", {"tool_profile": "corp_tools"}, "tool_invocation"),
        ("mcp", {"tool_profile": "local_files"}, "file_access"),
    ],
)
def test_resolve_profile_for_node_returns_expected_profile(
    resolver: ProfileResolver,
    workflow_spec: SimpleNamespace,
    node_type: str,
    config: dict[str, object],
    expected_contract: str,
) -> None:
    node = make_node(node_type, config)

    profile = resolver.resolve_profile_for_node(workflow_spec, node)

    assert profile is not None
    assert profile.contract == expected_contract


@pytest.mark.parametrize(
    ("node_type", "config"),
    [
        ("llm", {}),
        ("api", {}),
        ("mcp", {}),
    ],
)
def test_resolve_profile_for_node_missing_profile_name_raises(
    resolver: ProfileResolver,
    workflow_spec: SimpleNamespace,
    node_type: str,
    config: dict[str, object],
) -> None:
    node = make_node(node_type, config)

    with pytest.raises(ProfileResolutionError):
        resolver.resolve_profile_for_node(workflow_spec, node)


@pytest.mark.parametrize(
    "node_type",
    ["deterministic_transform", "human_gate", "unknown_type", "llm_generate"],
)
def test_resolve_profile_for_unsupported_node_type_returns_none(
    resolver: ProfileResolver,
    workflow_spec: SimpleNamespace,
    node_type: str,
) -> None:
    node = make_node(node_type, {})

    assert resolver.resolve_profile_for_node(workflow_spec, node) is None


def test_resolve_profile_for_node_unknown_profile_reference_raises(
    resolver: ProfileResolver,
    workflow_spec: SimpleNamespace,
) -> None:
    node = make_node("llm", {"llm_profile": "default_llm", "rag": {"profile": "unknown_rag"}})

    with pytest.raises(ProfileResolutionError):
        resolver.resolve_profile_for_node(workflow_spec, node)


def test_resolve_profile_for_node_api_accepts_tool_or_file_contract(
    resolver: ProfileResolver,
    workflow_spec: SimpleNamespace,
) -> None:
    node = make_node("api", {"tool_profile": "corp_tools"})
    profile = resolver.resolve_profile_for_node(workflow_spec, node)
    assert profile is not None
    assert profile.contract == "tool_invocation"
