from __future__ import annotations

from agent_platform.integrations.rag_dataset_service import RAGNodeBindingService
from agent_platform.ui_api.definition_read_model_service import DefinitionReadModelService
from agent_platform.workflow_definitions import DefinitionValidationService


class _UnusedDefinitionService:
    pass


class _FakeDefinitionService:
    def __init__(self, yaml_text: str, updated_at: str) -> None:
        self._yaml_text = yaml_text
        self._updated_at = updated_at

    def list_definitions(self, *, include_archived: bool = False):
        return [
            type(
                "Meta",
                (),
                {
                    "workflow_id": "sample_workflow",
                    "workflow_name": "Sample Workflow",
                    "version": "0.1.0",
                    "updated_at": self._updated_at,
                    "is_archived": False,
                },
            )()
        ]

    def get_definition(self, workflow_id: str, *, include_archived: bool = False):
        return type(
            "Doc",
            (),
            {
                "workflow_id": workflow_id,
                "workflow_name": "Sample Workflow",
                "version": "0.1.0",
                "description": None,
                "yaml_text": self._yaml_text,
                "updated_at": self._updated_at,
                "is_archived": False,
                "source_path": None,
            },
        )()


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


def test_build_graph_editor_view_collects_edge_connection_candidates_and_selected_outgoing() -> None:
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
  - id: publish
    name: Publish
    type: deterministic_transform
edges:
  - from: review
    to: publish
"""
    service = _build_service()

    view = service.build_graph_editor_view(
        yaml_text=yaml_text,
        selected_tab='nodes',
        selected_node_id='review',
    )

    assert view.selected_node_editor is not None
    assert [item.node_id for item in view.selected_node_editor.edge_connection_candidates] == ['draft', 'publish']
    assert [item.node_id for item in view.selected_node_editor.selected_outgoing_connections] == ['publish']


def test_build_graph_editor_view_sets_selected_rag_dataset_from_node_binding(tmp_path) -> None:
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: review
    name: Review
    type: llm
edges: []
"""
    binding_service = RAGNodeBindingService(bindings_path=tmp_path / "bindings.json")
    binding_service.set_dataset_id(workflow_id="sample_workflow", node_id="review", dataset_id="kb-1")
    service = DefinitionReadModelService(
        definition_service=_UnusedDefinitionService(),
        validation_service=DefinitionValidationService(),
        rag_node_binding_service=binding_service,
    )

    view = service.build_graph_editor_view(
        yaml_text=yaml_text,
        selected_tab='nodes',
        selected_node_id='review',
    )

    assert view.selected_node_editor is not None
    assert view.selected_node_editor.selected_rag_dataset_id == 'kb-1'


def test_build_graph_editor_view_exposes_llm_task_for_llm_node() -> None:
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: review
    name: Review
    type: llm
    config:
      task: assessment
edges: []
"""
    service = _build_service()

    view = service.build_graph_editor_view(
        yaml_text=yaml_text,
        selected_tab='nodes',
        selected_node_id='review',
    )

    assert view.selected_node_editor is not None
    assert view.selected_node_editor.llm_task == 'assessment'


def test_build_graph_editor_view_exposes_extended_llm_config_fields() -> None:
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: extractor
    name: Extractor
    type: llm
    config:
      task: extract
      temperature: 0.4
      assessment_options:
        - pass
        - rework
      assessment_routes:
        pass: publish
        rework: rewrite
      extract_fields:
        - company_name
        - invoice_no
      extract_output_format: markdown
edges: []
"""
    service = _build_service()

    view = service.build_graph_editor_view(
        yaml_text=yaml_text,
        selected_tab='nodes',
        selected_node_id='extractor',
    )

    assert view.selected_node_editor is not None
    assert view.selected_node_editor.llm_temperature == '0.4'
    assert view.selected_node_editor.llm_assessment_options == 'pass\nrework'
    assert 'pass: publish' in view.selected_node_editor.llm_assessment_routes
    assert view.selected_node_editor.llm_extract_fields == 'company_name\ninvoice_no'
    assert view.selected_node_editor.llm_extract_output_format == 'markdown'


def test_build_definition_summaries_formats_updated_at_as_yyyy_mm_dd_hh_mm_ss() -> None:
    yaml_text = """
workflow_id: sample_workflow
workflow_name: Sample Workflow
nodes:
  - id: start
    name: Start
    type: llm_generate
edges: []
"""
    service = DefinitionReadModelService(
        definition_service=_FakeDefinitionService(yaml_text, "2026-04-17T10:23:45+00:00"),
        validation_service=DefinitionValidationService(),
    )

    summaries = service.build_definition_summaries()

    assert summaries[0].updated_at == "2026-04-17 10:23:45"
