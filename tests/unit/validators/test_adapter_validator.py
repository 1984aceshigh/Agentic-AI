from __future__ import annotations

from agent_platform.models import WorkflowSpec
from agent_platform.validators import validate_profile_contracts


def make_valid_workflow_dict() -> dict:
    return {
        "schema_version": "0.1",
        "workflow": {"id": "sample_workflow", "name": "Sample Workflow"},
        "runtime": {"start_node": "step1", "end_nodes": ["step2"]},
        "integrations": {
            "llm_profiles": {
                "default_llm": {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "contract": "llm_completion",
                    "capabilities": ["chat"],
                }
            },
            "memory_profiles": {
                "default_memory": {
                    "backend": "sqlite",
                    "contract": "memory_store",
                    "capabilities": ["read", "write"],
                }
            },
            "rag_profiles": {
                "default_rag": {
                    "backend": "pgvector",
                    "collection": "kb",
                    "embedding_model": "text-embedding-3-large",
                    "contract": "vector_retriever",
                    "capabilities": ["search"],
                }
            },
            "tool_profiles": {
                "default_tool": {
                    "contract": "tool_invocation",
                    "capabilities": ["invoke_tool"],
                }
            },
        },
        "nodes": [
            {
                "id": "step1",
                "type": "llm_generate",
                "name": "Step 1",
                "config": {"llm_profile": "default_llm"},
                "output": {"key": "step1_result"},
            },
            {
                "id": "step2",
                "type": "human_gate",
                "name": "Step 2",
                "input": {"from": [{"node": "step1", "key": "step1_result"}]},
            },
        ],
        "edges": [{"from": "step1", "to": "step2"}],
    }


def make_spec() -> WorkflowSpec:
    return WorkflowSpec.model_validate(make_valid_workflow_dict())


def test_llm_profile_with_llm_completion_contract_is_valid() -> None:
    issues = validate_profile_contracts(make_spec())
    assert issues == []


def test_llm_profile_with_invalid_contract_returns_error() -> None:
    spec = make_spec()
    spec.integrations.llm_profiles["default_llm"].contract = "file_access"  # type: ignore[assignment]

    issues = validate_profile_contracts(spec)

    assert any(issue.code == "invalid_contract_type" for issue in issues)


def test_memory_profile_with_invalid_contract_returns_error() -> None:
    spec = make_spec()
    spec.integrations.memory_profiles["default_memory"].contract = "tool_invocation"  # type: ignore[assignment]

    issues = validate_profile_contracts(spec)

    assert any(issue.code == "invalid_contract_type" for issue in issues)


def test_rag_profile_with_invalid_contract_returns_error() -> None:
    spec = make_spec()
    spec.integrations.rag_profiles["default_rag"].contract = "memory_store"  # type: ignore[assignment]

    issues = validate_profile_contracts(spec)

    assert any(issue.code == "invalid_contract_type" for issue in issues)


def test_tool_profile_with_tool_invocation_contract_is_valid() -> None:
    issues = validate_profile_contracts(make_spec())
    assert not any(issue.code == "invalid_contract_type" for issue in issues)


def test_tool_profile_with_file_access_contract_is_valid() -> None:
    spec = make_spec()
    spec.integrations.tool_profiles["default_tool"].contract = "file_access"  # type: ignore[assignment]
    spec.integrations.tool_profiles["default_tool"].capabilities = ["read"]

    issues = validate_profile_contracts(spec)

    assert not any(issue.code == "invalid_contract_type" for issue in issues)


def test_unknown_capability_returns_warning() -> None:
    spec = make_spec()
    spec.integrations.llm_profiles["default_llm"].capabilities.append("unknown_capability")

    issues = validate_profile_contracts(spec)

    assert any(issue.code == "unknown_capability" for issue in issues)


def test_missing_required_capability_returns_warning() -> None:
    spec = make_spec()
    spec.nodes[0].config["required_capabilities"] = ["json_output"]

    issues = validate_profile_contracts(spec)

    assert any(issue.code == "missing_required_capability" for issue in issues)


def test_missing_connection_ref_with_adapter_ref_returns_warning() -> None:
    spec = make_spec()
    spec.integrations.llm_profiles["default_llm"].adapter_ref = "openai_responses"
    spec.integrations.llm_profiles["default_llm"].connection_ref = None

    issues = validate_profile_contracts(spec)

    assert any(issue.code == "missing_connection_ref" for issue in issues)
