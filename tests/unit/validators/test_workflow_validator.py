from __future__ import annotations

from copy import deepcopy

from agent_platform.models import RetrySpec, WorkflowSpec
from agent_platform.validators import has_errors, validate_workflow_spec


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
                    "capabilities": ["chat", "json_output"],
                }
            },
            "memory_profiles": {},
            "rag_profiles": {},
            "tool_profiles": {},
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
        "display": {"mermaid": {"direction": "TD"}},
    }


def make_spec() -> WorkflowSpec:
    return WorkflowSpec.model_validate(make_valid_workflow_dict())


def test_minimal_valid_workflow_returns_no_issues() -> None:
    issues = validate_workflow_spec(make_spec())
    assert issues == []


def test_warning_only_case_has_no_errors() -> None:
    data = make_valid_workflow_dict()
    data["schema_version"] = "0.2"

    issues = validate_workflow_spec(WorkflowSpec.model_validate(data))

    assert any(issue.severity.value == "WARNING" for issue in issues)
    assert has_errors(issues) is False


def test_start_node_mismatch_returns_error() -> None:
    spec = make_spec()
    spec.runtime.start_node = "missing"

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "missing_start_node_ref" for issue in issues)
    assert has_errors(issues) is True


def test_end_node_mismatch_returns_error() -> None:
    spec = make_spec()
    spec.runtime.end_nodes = ["missing"]

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "missing_end_node_ref" for issue in issues)


def test_duplicate_node_id_returns_error() -> None:
    data = make_valid_workflow_dict()
    duplicate = deepcopy(data["nodes"][0])
    data["nodes"].append(duplicate)

    spec = WorkflowSpec.model_validate(data)
    issues = validate_workflow_spec(spec)

    assert any(issue.code == "duplicate_node_id" for issue in issues)


def test_edge_reference_to_missing_node_returns_error() -> None:
    spec = make_spec()
    spec.edges[0].to_node = "missing"

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "invalid_edge_ref" for issue in issues)


def test_unreachable_end_node_returns_error() -> None:
    spec = make_spec()
    spec.edges = []

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "unreachable_end_node" for issue in issues)


def test_unreachable_non_end_node_returns_warning() -> None:
    data = make_valid_workflow_dict()
    data["nodes"].append({"id": "step3", "type": "human_gate", "name": "Step 3"})
    spec = WorkflowSpec.model_validate(data)

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "unreachable_node" and issue.severity.value == "WARNING" for issue in issues)


def test_retry_zero_returns_error() -> None:
    spec = make_spec()
    spec.nodes[0].retry = RetrySpec(max_attempts=0)

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "invalid_retry_value" for issue in issues)


def test_empty_node_name_returns_warning() -> None:
    spec = make_spec()
    spec.nodes[0].name = ""

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "empty_node_name" for issue in issues)


def test_self_loop_edge_returns_warning() -> None:
    spec = make_spec()
    spec.edges[0].to_node = "step1"

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "self_loop_edge" for issue in issues)


def test_missing_input_source_node_returns_error() -> None:
    spec = make_spec()
    spec.nodes[1].input.from_[0].node = "missing"

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "invalid_input_ref" for issue in issues)


def test_mismatched_input_key_returns_warning() -> None:
    spec = make_spec()
    spec.nodes[1].input.from_[0].key = "different_key"

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "mismatched_output_key_ref" for issue in issues)


def test_missing_llm_profile_returns_error() -> None:
    spec = make_spec()
    spec.nodes[0].config = {}

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "missing_required_profile" for issue in issues)


def test_unknown_llm_profile_returns_error() -> None:
    spec = make_spec()
    spec.nodes[0].config["llm_profile"] = "unknown"

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "unknown_profile_ref" for issue in issues)


def test_legacy_deterministic_transform_is_normalized_to_llm_and_requires_llm_profile() -> None:
    data = make_valid_workflow_dict()
    data["nodes"][0] = {
        "id": "step1",
        "type": "deterministic_transform",
        "name": "Transform",
        "config": {},
        "output": {"key": "step1_result"},
    }
    spec = WorkflowSpec.model_validate(data)

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "missing_required_profile" for issue in issues)


def test_legacy_deterministic_transform_with_custom_type_still_requires_llm_profile() -> None:
    data = make_valid_workflow_dict()
    data["nodes"][0] = {
        "id": "step1",
        "type": "deterministic_transform",
        "name": "Transform",
        "config": {"transform_type": "custom_transform"},
        "output": {"key": "step1_result"},
    }
    spec = WorkflowSpec.model_validate(data)

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "missing_required_profile" for issue in issues)


def test_invalid_gate_type_returns_error() -> None:
    spec = make_spec()
    spec.nodes[1].config = {"gate_type": "approve"}

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "invalid_gate_type" for issue in issues)


def test_invalid_on_reject_ref_returns_error() -> None:
    spec = make_spec()
    spec.nodes[1].config = {"on_reject": "missing"}

    issues = validate_workflow_spec(spec)

    assert any(issue.code == "invalid_on_reject_ref" for issue in issues)
