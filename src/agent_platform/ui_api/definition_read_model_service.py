from __future__ import annotations

from typing import Any

import yaml

from agent_platform.workflow_definitions import (
    DefinitionValidationService,
    WorkflowDefinitionDocument,
    WorkflowDefinitionService,
)

from .definition_view_models import (
    EdgeEditorView,
    EdgeSummaryView,
    GraphEditorView,
    NodeEditorView,
    NodeSummaryView,
    WorkflowDefinitionSummaryView,
)


class DefinitionReadModelService:
    def __init__(
        self,
        definition_service: WorkflowDefinitionService,
        validation_service: DefinitionValidationService,
    ) -> None:
        self._definition_service = definition_service
        self._validation_service = validation_service

    def build_definition_summaries(self, *, include_archived: bool = False) -> list[WorkflowDefinitionSummaryView]:
        items = self._definition_service.list_definitions(include_archived=include_archived)
        summaries: list[WorkflowDefinitionSummaryView] = []
        for item in items:
            validation = self._validation_service.validate_yaml_text(
                self._definition_service.get_definition(item.workflow_id, include_archived=item.is_archived).yaml_text
            )
            summaries.append(
                WorkflowDefinitionSummaryView(
                    workflow_id=item.workflow_id,
                    workflow_name=item.workflow_name,
                    version=item.version,
                    updated_at=item.updated_at,
                    is_archived=item.is_archived,
                    validation_status='valid' if validation.is_valid else 'invalid',
                    node_count=validation.node_count,
                    edge_count=validation.edge_count,
                )
            )
        return summaries

    def build_graph_editor_view(
        self,
        *,
        workflow_id: str | None = None,
        selected_node_id: str | None = None,
        selected_tab: str = 'overview',
        yaml_text: str | None = None,
        include_archived: bool = False,
        is_dirty: bool = False,
    ) -> GraphEditorView:
        document = self._resolve_document(workflow_id=workflow_id, yaml_text=yaml_text, include_archived=include_archived)
        validation = self._validation_service.validate_yaml_text(document.yaml_text)
        node_summaries = [
            NodeSummaryView(
                node_id=str(item.get('node_id', '')),
                node_name=str(item.get('node_name') or item.get('node_id') or ''),
                node_type=str(item.get('node_type') or ''),
                group=item.get('group'),
                selected=str(item.get('node_id')) == selected_node_id,
            )
            for item in validation.node_summaries
        ]
        edge_summaries = [
            EdgeSummaryView(
                from_node_id=str(item.get('from_node_id') or ''),
                to_node_id=str(item.get('to_node_id') or ''),
                label=(str(item.get('label')) if item.get('label') is not None else None),
            )
            for item in validation.edge_summaries
        ]
        selected_editor = self._build_node_editor(document.yaml_text, selected_node_id, edge_summaries)
        return GraphEditorView(
            workflow_id=validation.workflow_id or document.workflow_id,
            workflow_name=validation.workflow_name or document.workflow_name,
            version=validation.version or document.version,
            description=validation.description or document.description,
            is_archived=document.is_archived,
            selected_node_id=selected_node_id,
            selected_tab=selected_tab,
            yaml_text=document.yaml_text,
            mermaid_text=validation.mermaid_text or 'graph TD\n',
            node_summaries=node_summaries,
            edge_summaries=edge_summaries,
            selected_node_editor=selected_editor,
            edge_editor=EdgeEditorView(),
            validation_status='valid' if validation.is_valid else 'invalid',
            validation_errors=list(validation.validation_errors),
            validation_warnings=list(validation.warnings),
            parse_errors=list(validation.parse_errors),
            node_count=validation.node_count or 0,
            edge_count=validation.edge_count or 0,
            is_dirty=is_dirty,
        )

    def _resolve_document(
        self,
        *,
        workflow_id: str | None,
        yaml_text: str | None,
        include_archived: bool,
    ) -> WorkflowDefinitionDocument:
        if yaml_text is not None:
            validation = self._validation_service.validate_yaml_text(yaml_text)
            resolved_workflow_id = validation.workflow_id or workflow_id or 'unsaved_workflow'
            return WorkflowDefinitionDocument(
                workflow_id=resolved_workflow_id,
                workflow_name=validation.workflow_name or resolved_workflow_id,
                version=validation.version,
                description=validation.description,
                yaml_text=yaml_text,
                updated_at=None,
                is_archived=False,
                source_path=None,
            )
        if workflow_id is not None:
            return self._definition_service.get_definition(workflow_id, include_archived=include_archived)
        return self._definition_service.create_empty_definition()

    def _build_node_editor(
        self,
        yaml_text: str,
        selected_node_id: str | None,
        edge_summaries: list[EdgeSummaryView],
    ) -> NodeEditorView | None:
        if not selected_node_id:
            return None
        parsed = yaml.safe_load(yaml_text) or {}
        if not isinstance(parsed, dict):
            return None
        node_data = _find_node_payload(parsed, selected_node_id)
        if node_data is None:
            return None
        basic_keys = {'id', 'node_id', 'name', 'display_name', 'type', 'node_type', 'group'}
        advanced = {k: v for k, v in node_data.items() if k not in basic_keys}
        incoming = [edge for edge in edge_summaries if edge.to_node_id == selected_node_id]
        outgoing = [edge for edge in edge_summaries if edge.from_node_id == selected_node_id]
        return NodeEditorView(
            node_id=selected_node_id,
            node_name=str(node_data.get('name') or node_data.get('display_name') or selected_node_id),
            node_type=str(node_data.get('type') or node_data.get('node_type') or ''),
            group=(str(node_data['group']) if node_data.get('group') is not None else None),
            advanced_yaml_fragment=yaml.safe_dump(advanced, allow_unicode=True, sort_keys=False).strip() if advanced else '',
            incoming_edges=incoming,
            outgoing_edges=outgoing,
            deletable=not bool(incoming or outgoing),
        )


def _find_node_payload(parsed: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    nodes = parsed.get('nodes')
    if isinstance(nodes, list):
        for item in nodes:
            if not isinstance(item, dict):
                continue
            if str(item.get('id') or item.get('node_id') or '') == node_id:
                return dict(item)
    elif isinstance(nodes, dict):
        payload = nodes.get(node_id)
        if isinstance(payload, dict):
            result = dict(payload)
            result.setdefault('id', node_id)
            return result
    return None
