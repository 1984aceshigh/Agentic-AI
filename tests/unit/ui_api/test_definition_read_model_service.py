from __future__ import annotations

from agent_platform.ui_api.definition_read_model_service import DefinitionReadModelService
from agent_platform.workflow_definitions import DefinitionValidationService


class _UnusedDefinitionService:
    pass


def _build_service() -> DefinitionReadModelService:
    return DefinitionReadModelService(
        definition_service=_UnusedDefinitionService(),
        validation_service=DefinitionValidationService(),
    )


def test_build_graph_editor_view_collects_input_definition_candidates_from_previous_nodes() -> None:
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: draft
    name: Draft
    type: llm_generate
  - id: planner
    name: Planner
    type: deterministic_transform
    output:
      key: plan_schema
  - id: review
    name: Review
    type: llm_review
edges:
  - from: draft
    to: planner
  - from: planner
    to: review
"""
    service = _build_service()

    view = service.build_graph_editor_view(
        yaml_text=yaml_text,
        selected_tab='nodes',
        selected_node_id='review',
    )

    assert view.selected_node_editor is not None
    candidates = view.selected_node_editor.input_definition_candidates
    assert [item.node_id for item in candidates] == ['draft', 'planner']
    assert [item.ref_expression for item in candidates] == [
        'ref: draft.result',
        'ref: planner.plan_schema',
    ]


def test_build_graph_editor_view_first_node_has_no_input_definition_candidates() -> None:
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: draft
    name: Draft
    type: llm_generate
  - id: review
    name: Review
    type: llm_review
edges:
  - from: draft
    to: review
"""
    service = _build_service()

    view = service.build_graph_editor_view(
        yaml_text=yaml_text,
        selected_tab='nodes',
        selected_node_id='draft',
    )

    assert view.selected_node_editor is not None
    assert view.selected_node_editor.input_definition_candidates == []
