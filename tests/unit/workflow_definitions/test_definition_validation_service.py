from __future__ import annotations

from agent_platform.graph.builder import build_graph_model
from agent_platform.graph.mermaid import build_mermaid
from agent_platform.validators.workflow_validator import has_errors, validate_workflow_spec
from agent_platform.workflow_definitions import (
    DefinitionValidationService,
    FileWorkflowDefinitionRepository,
    WorkflowDefinitionService,
)
from agent_platform.yaml_io.loader import load_workflow_yaml_text


MINIMAL_EDITOR_YAML = """
workflow_id: new_workflow
workflow_name: New Workflow
version: 0.1.0
nodes:
  - id: start_node
    name: Start Node
    type: llm_generate
  - id: end_node
    name: End Node
    type: deterministic_transform
edges:
  - from: start_node
    to: end_node
"""


def _build_definition_validation_service() -> DefinitionValidationService:
    def _validate(spec: object) -> list[str]:
        issues = validate_workflow_spec(spec)
        if not has_errors(issues):
            return []
        return [str(issue.message) for issue in issues]

    return DefinitionValidationService(
        loader=load_workflow_yaml_text,
        validator=_validate,
        graph_builder=build_graph_model,
        mermaid_builder=build_mermaid,
    )


def test_validation_service_builds_fallback_graph_when_structured_loader_fails() -> None:
    service = _build_definition_validation_service()

    result = service.validate_yaml_text(MINIMAL_EDITOR_YAML)

    assert result.is_valid is True
    assert result.graph is not None
    assert result.graph.workflow_id == "new_workflow"
    assert result.graph.workflow_name == "New Workflow"
    assert result.graph.start_node == "start_node"
    assert result.graph.end_nodes == ["end_node"]
    assert set(result.graph.nodes.keys()) == {"start_node", "end_node"}
    assert len(result.graph.edges) == 1
    assert result.graph.edges[0].from_node == "start_node"
    assert result.graph.edges[0].to_node == "end_node"
    assert any("fallback" in warning.lower() for warning in result.warnings)


def test_definition_service_save_updates_runtime_graphs_for_editor_yaml(tmp_path) -> None:
    workflow_graphs: dict[str, object] = {}
    latest_execution_ids: dict[str, str | None] = {}
    validation_service = _build_definition_validation_service()
    repository = FileWorkflowDefinitionRepository(tmp_path / "workflow_definitions")
    service = WorkflowDefinitionService(
        repository,
        validation_service,
        workflow_graphs=workflow_graphs,
        latest_execution_ids=latest_execution_ids,
    )

    saved, validation = service.save_definition(MINIMAL_EDITOR_YAML)

    assert saved.workflow_id == "new_workflow"
    assert validation.is_valid is True
    assert "new_workflow" in workflow_graphs
    graph = workflow_graphs["new_workflow"]
    assert graph.workflow_id == "new_workflow"
    assert set(graph.nodes.keys()) == {"start_node", "end_node"}
    assert latest_execution_ids["new_workflow"] is None


def test_validation_service_uses_unified_mermaid_builder_when_not_injected() -> None:
    service = DefinitionValidationService()
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: draft
    name: Draft
    type: llm_generate
    group: review
  - id: check
    name: Check
    type: llm_review
    group: review
edges:
  - from: draft
    to: check
"""

    result = service.validate_yaml_text(yaml_text)

    assert result.is_valid is True
    assert result.mermaid_text is not None
    assert "flowchart TD" in result.mermaid_text
    assert 'subgraph group_1["review"]' in result.mermaid_text
    assert "(llm_generate)" in result.mermaid_text
    assert "(llm_review)" in result.mermaid_text
