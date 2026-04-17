from __future__ import annotations

from datetime import datetime
from typing import Any

import yaml

from agent_platform.integrations import RAGDatasetService, RAGNodeBindingService
from agent_platform.workflow_definitions import (
    DefinitionValidationService,
    WorkflowDefinitionDocument,
    WorkflowDefinitionService,
)
from agent_platform.workflow_definitions.node_type_migration import normalize_workflow_node_types

from .definition_view_models import (
    EdgeConnectionNodeView,
    EdgeEditorView,
    EdgeSummaryView,
    GraphEditorView,
    InputDefinitionCandidateView,
    NodeEditorView,
    RAGDatasetOptionView,
    NodeSummaryView,
    WorkflowDefinitionSummaryView,
)


class DefinitionReadModelService:
    def __init__(
        self,
        definition_service: WorkflowDefinitionService,
        validation_service: DefinitionValidationService,
        rag_dataset_service: RAGDatasetService | None = None,
        rag_node_binding_service: RAGNodeBindingService | None = None,
    ) -> None:
        self._definition_service = definition_service
        self._validation_service = validation_service
        self._rag_dataset_service = rag_dataset_service
        self._rag_node_binding_service = rag_node_binding_service

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
                    updated_at=_format_datetime_text(item.updated_at),
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
        selected_tab: str = 'nodes',
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
        selected_editor = self._build_node_editor(
            document.yaml_text,
            workflow_id=validation.workflow_id or document.workflow_id,
            selected_node_id=selected_node_id,
            edge_summaries=edge_summaries,
        )
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
            rag_dataset_options=self._build_rag_dataset_options(),
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
        *,
        workflow_id: str,
        selected_node_id: str | None,
        edge_summaries: list[EdgeSummaryView],
    ) -> NodeEditorView | None:
        if not selected_node_id:
            return None
        parsed = yaml.safe_load(yaml_text) or {}
        if not isinstance(parsed, dict):
            return None
        parsed, _ = normalize_workflow_node_types(parsed)
        node_data = _find_node_payload(parsed, selected_node_id)
        if node_data is None:
            return None
        input_definition_candidates = _collect_input_definition_candidates(parsed, selected_node_id)
        config = node_data.get('config') if isinstance(node_data.get('config'), dict) else {}
        node_type = str(node_data.get('type') or node_data.get('node_type') or '')
        is_llm_node = node_type == 'llm'
        basic_keys = {'id', 'node_id', 'name', 'display_name', 'type', 'node_type', 'group'}
        advanced = {k: v for k, v in node_data.items() if k not in basic_keys}
        incoming = [edge for edge in edge_summaries if edge.to_node_id == selected_node_id]
        outgoing = [edge for edge in edge_summaries if edge.from_node_id == selected_node_id]
        edge_connection_candidates = _collect_edge_connection_candidates(parsed, selected_node_id)
        selected_outgoing_connections = [
            item
            for item in edge_connection_candidates
            if any(edge.to_node_id == item.node_id for edge in outgoing)
        ]
        rag_dataset_options = self._build_rag_dataset_options()
        selected_rag_dataset_id = self._resolve_selected_rag_dataset_id(
            workflow_id=workflow_id,
            node_id=selected_node_id,
            config=config,
        )
        return NodeEditorView(
            node_id=selected_node_id,
            node_name=str(node_data.get('name') or node_data.get('display_name') or selected_node_id),
            node_type=node_type,
            group=(str(node_data['group']) if node_data.get('group') is not None else None),
            is_llm_node=is_llm_node,
            llm_task=_normalize_llm_task(config.get('task')),
            llm_temperature=_stringify_scalar(config.get('temperature')),
            llm_prompt=str(config.get('prompt') or ''),
            llm_input_definition=str(config.get('input_definition') or ''),
            llm_output_format=str(config.get('output_format') or ''),
            llm_assessment_options='\n'.join(_string_list(config.get('assessment_options'))),
            llm_assessment_routes=_dump_yaml_mapping(config.get('assessment_routes')),
            llm_extract_fields='\n'.join(_string_list(config.get('extract_fields'))),
            llm_extract_output_format=_normalize_extract_output_format(config.get('extract_output_format')),
            input_definition_candidates=input_definition_candidates,
            edge_connection_candidates=edge_connection_candidates,
            selected_outgoing_connections=selected_outgoing_connections,
            rag_dataset_options=rag_dataset_options,
            selected_rag_dataset_id=selected_rag_dataset_id,
            advanced_yaml_fragment=yaml.safe_dump(advanced, allow_unicode=True, sort_keys=False).strip() if advanced else '',
            incoming_edges=incoming,
            outgoing_edges=outgoing,
            deletable=not bool(incoming or outgoing),
        )

    def _build_rag_dataset_options(self) -> list[RAGDatasetOptionView]:
        if self._rag_dataset_service is None:
            return []
        options: list[RAGDatasetOptionView] = []
        for item in self._rag_dataset_service.list_datasets():
            options.append(
                RAGDatasetOptionView(
                    dataset_id=item.dataset_id,
                    name=item.name,
                    source_filename=item.source_filename,
                    source_type=item.source_type,
                    chunk_count=item.chunk_count,
                )
            )
        return options

    def _resolve_selected_rag_dataset_id(
        self,
        *,
        workflow_id: str,
        node_id: str,
        config: dict[str, Any],
    ) -> str | None:
        if self._rag_node_binding_service is not None:
            bound = self._rag_node_binding_service.get_dataset_id(workflow_id=workflow_id, node_id=node_id)
            if bound:
                return bound
        rag = config.get('rag')
        if isinstance(rag, dict):
            profile = rag.get('profile')
            if isinstance(profile, str) and profile.strip():
                return profile.strip()
        return None


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


def _collect_input_definition_candidates(
    parsed: dict[str, Any],
    selected_node_id: str,
) -> list[InputDefinitionCandidateView]:
    ordered_nodes = _ordered_node_payloads(parsed)
    selected_index = next(
        (index for index, node in enumerate(ordered_nodes) if node['node_id'] == selected_node_id),
        -1,
    )
    if selected_index <= 0:
        return []

    candidates: list[InputDefinitionCandidateView] = []
    for node in ordered_nodes[:selected_index]:
        output_key = 'result'
        output_payload = node.get('output')
        if isinstance(output_payload, dict) and isinstance(output_payload.get('key'), str):
            normalized = str(output_payload.get('key')).strip()
            if normalized:
                output_key = normalized

        candidates.append(
            InputDefinitionCandidateView(
                node_id=node['node_id'],
                node_name=node['node_name'],
                output_key=output_key,
                ref_expression=f"ref: {node['node_id']}.{output_key}",
            )
        )
    return candidates


def _ordered_node_payloads(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = parsed.get('nodes')
    ordered: list[dict[str, Any]] = []
    if isinstance(nodes, list):
        for item in nodes:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get('id') or item.get('node_id') or '').strip()
            if not node_id:
                continue
            ordered.append(
                {
                    'node_id': node_id,
                    'node_name': str(item.get('name') or item.get('display_name') or node_id),
                    'output': item.get('output'),
                }
            )
        return ordered

    if isinstance(nodes, dict):
        for node_id, payload in nodes.items():
            if not isinstance(payload, dict):
                continue
            ordered.append(
                {
                    'node_id': str(node_id),
                    'node_name': str(payload.get('name') or payload.get('display_name') or node_id),
                    'output': payload.get('output'),
                }
            )
    return ordered


def _collect_edge_connection_candidates(
    parsed: dict[str, Any],
    selected_node_id: str,
) -> list[EdgeConnectionNodeView]:
    return [
        EdgeConnectionNodeView(
            node_id=node['node_id'],
            node_name=node['node_name'],
            node_type=str(node.get('node_type') or ''),
        )
        for node in _ordered_node_payloads_with_type(parsed)
        if node['node_id'] != selected_node_id
    ]


def _ordered_node_payloads_with_type(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = parsed.get('nodes')
    ordered: list[dict[str, Any]] = []
    if isinstance(nodes, list):
        for item in nodes:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get('id') or item.get('node_id') or '').strip()
            if not node_id:
                continue
            ordered.append(
                {
                    'node_id': node_id,
                    'node_name': str(item.get('name') or item.get('display_name') or node_id),
                    'node_type': str(item.get('type') or item.get('node_type') or ''),
                }
            )
        return ordered

    if isinstance(nodes, dict):
        for node_id, payload in nodes.items():
            if not isinstance(payload, dict):
                continue
            ordered.append(
                {
                    'node_id': str(node_id),
                    'node_name': str(payload.get('name') or payload.get('display_name') or node_id),
                    'node_type': str(payload.get('type') or payload.get('node_type') or ''),
                }
            )
    return ordered


def _format_datetime_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return parsed.strftime('%Y-%m-%d %H:%M:%S')


def _normalize_llm_task(raw_task: Any) -> str:
    normalized = str(raw_task or 'generate').strip().lower()
    if normalized in {'assessment', 'extract', 'generate'}:
        return normalized
    if normalized in {'review', 'classify', 'judge'}:
        return 'assessment'
    return 'generate'


def _normalize_extract_output_format(raw_value: Any) -> str:
    normalized = str(raw_value or 'json').strip().lower()
    if normalized == 'plain text':
        normalized = 'plain_text'
    if normalized not in {'json', 'yaml', 'markdown', 'plain_text'}:
        return 'json'
    return normalized


def _stringify_scalar(value: Any) -> str:
    if value is None:
        return ''
    return str(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dump_yaml_mapping(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ''
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()
