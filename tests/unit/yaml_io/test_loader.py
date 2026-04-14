from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.models import WorkflowSpec
from agent_platform.yaml_io import (
    WorkflowFileReadError,
    WorkflowModelValidationError,
    WorkflowYamlParseError,
    load_workflow_dict,
    load_workflow_yaml,
    load_workflow_yaml_text,
)


MINIMAL_VALID_YAML = """
schema_version: "0.1"

workflow:
  id: "sample_workflow"
  name: "Sample Workflow"

runtime:
  start_node: "step1"
  end_nodes:
    - "step2"

integrations:
  llm_profiles: {}
  memory_profiles: {}
  rag_profiles: {}
  tool_profiles: {}

nodes:
  - id: "step1"
    type: "llm_generate"
    name: "Step 1"
    output:
      key: "step1_result"

  - id: "step2"
    type: "human_gate"
    name: "Step 2"
    input:
      from:
        - node: "step1"
          key: "step1_result"

edges:
  - from: "step1"
    to: "step2"

display:
  mermaid:
    direction: "TD"
"""

BROKEN_YAML = """
schema_version: "0.1"
workflow:
  id: "broken"
  name: "Broken"
runtime:
  start_node: "a"
  end_nodes:
    - "b"
nodes:
  - id: "a"
    type: "llm_generate"
    name: "A"
edges:
  - from: "a"
    to: "b
"""

MODEL_ERROR_YAML = """
schema_version: "0.1"
workflow:
  id: "missing_nodes"
  name: "Missing Nodes"

runtime:
  start_node: "a"
  end_nodes:
    - "b"

integrations:
  llm_profiles: {}
  memory_profiles: {}
  rag_profiles: {}
  tool_profiles: {}

nodes: []
edges: []
"""

TOP_LEVEL_LIST_YAML = """
- schema_version: "0.1"
- workflow:
    id: "sample"
    name: "Sample"
"""


def minimal_valid_dict() -> dict:
    return {
        "schema_version": "0.1",
        "workflow": {"id": "sample_workflow", "name": "Sample Workflow"},
        "runtime": {"start_node": "step1", "end_nodes": ["step2"]},
        "integrations": {
            "llm_profiles": {},
            "memory_profiles": {},
            "rag_profiles": {},
            "tool_profiles": {},
        },
        "nodes": [
            {
                "id": "step1",
                "type": "llm_generate",
                "name": "Step 1",
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


def test_load_workflow_yaml_text_returns_workflow_spec() -> None:
    spec = load_workflow_yaml_text(MINIMAL_VALID_YAML)

    assert isinstance(spec, WorkflowSpec)
    assert spec.workflow.id == "sample_workflow"
    assert spec.runtime.start_node == "step1"


def test_load_workflow_yaml_reads_from_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    path.write_text(MINIMAL_VALID_YAML, encoding="utf-8")

    spec = load_workflow_yaml(path)

    assert isinstance(spec, WorkflowSpec)
    assert spec.workflow.name == "Sample Workflow"


def test_load_workflow_dict_returns_workflow_spec() -> None:
    spec = load_workflow_dict(minimal_valid_dict())

    assert isinstance(spec, WorkflowSpec)
    assert spec.nodes[0].id == "step1"


def test_yaml_aliases_are_loaded_correctly() -> None:
    spec = load_workflow_yaml_text(MINIMAL_VALID_YAML)

    assert spec.nodes[1].input is not None
    assert spec.nodes[1].input.from_[0].node == "step1"
    assert spec.edges[0].from_node == "step1"
    assert spec.edges[0].to_node == "step2"


def test_syntax_error_yaml_raises_parse_error() -> None:
    with pytest.raises(WorkflowYamlParseError):
        load_workflow_yaml_text(BROKEN_YAML)


def test_missing_required_items_yaml_raises_model_validation_error() -> None:
    with pytest.raises(WorkflowModelValidationError) as exc_info:
        load_workflow_yaml_text(MODEL_ERROR_YAML)

    assert exc_info.value.errors


def test_empty_yaml_raises_model_validation_error() -> None:
    with pytest.raises(WorkflowModelValidationError) as exc_info:
        load_workflow_yaml_text("")

    assert exc_info.value.errors


def test_missing_file_raises_file_read_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(WorkflowFileReadError) as exc_info:
        load_workflow_yaml(missing_path)

    assert exc_info.value.source == str(missing_path)


def test_yaml_top_level_array_raises_model_validation_error() -> None:
    with pytest.raises(WorkflowModelValidationError) as exc_info:
        load_workflow_yaml_text(TOP_LEVEL_LIST_YAML)

    assert exc_info.value.errors


def test_parse_error_contains_line_and_column() -> None:
    with pytest.raises(WorkflowYamlParseError) as exc_info:
        load_workflow_yaml_text(BROKEN_YAML)

    assert exc_info.value.line is not None
    assert exc_info.value.column is not None


def test_model_validation_error_contains_pydantic_errors() -> None:
    invalid_data = {"schema_version": "0.1"}

    with pytest.raises(WorkflowModelValidationError) as exc_info:
        load_workflow_dict(invalid_data)

    assert exc_info.value.errors
    assert isinstance(exc_info.value.errors, list)


def test_file_read_failure_keeps_source_for_directory(tmp_path: Path) -> None:
    directory_path = tmp_path / "workflow_dir"
    directory_path.mkdir()

    with pytest.raises(WorkflowFileReadError) as exc_info:
        load_workflow_yaml(directory_path)

    assert exc_info.value.source == str(directory_path)
