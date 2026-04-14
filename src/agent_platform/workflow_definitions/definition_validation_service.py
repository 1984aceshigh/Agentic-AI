from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import yaml


@dataclass(slots=True)
class WorkflowDefinitionValidationResult:
    is_valid: bool
    yaml_text: str
    workflow_id: str | None = None
    workflow_name: str | None = None
    version: str | None = None
    description: str | None = None
    parse_errors: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    node_count: int | None = None
    edge_count: int | None = None
    mermaid_text: str | None = None
    node_summaries: list[dict[str, Any]] = field(default_factory=list)
    edge_summaries: list[dict[str, Any]] = field(default_factory=list)
    parsed_data: dict[str, Any] = field(default_factory=dict)
    graph: Any | None = None


class DefinitionValidationService:
    def __init__(
        self,
        *,
        loader: Callable[[str], Any] | None = None,
        validator: Callable[[Any], Any] | None = None,
        graph_builder: Callable[[Any], Any] | None = None,
        mermaid_builder: Callable[[Any], str] | None = None,
    ) -> None:
        self._loader = loader
        self._validator = validator
        self._graph_builder = graph_builder
        self._mermaid_builder = mermaid_builder

    def validate_yaml_text(self, yaml_text: str) -> WorkflowDefinitionValidationResult:
        parsed_result = self._parse_yaml(yaml_text)
        if parsed_result.parse_errors:
            return parsed_result

        loaded_spec: Any = parsed_result.parsed_data
        if self._loader is not None:
            try:
                loaded_spec = self._loader(yaml_text)
            except Exception as exc:  # pragma: no cover - depends on project loader
                parsed_result.validation_errors.append(str(exc))
                parsed_result.is_valid = False
                return parsed_result

        if self._validator is not None:
            try:
                validation_result = self._validator(loaded_spec)
                if isinstance(validation_result, list):
                    parsed_result.validation_errors.extend(str(item) for item in validation_result)
            except Exception as exc:  # pragma: no cover - depends on project validator
                parsed_result.validation_errors.append(str(exc))

        parsed_result.validation_errors.extend(self._fallback_validate(parsed_result.parsed_data))
        parsed_result.is_valid = not parsed_result.parse_errors and not parsed_result.validation_errors

        if self._graph_builder is not None and parsed_result.is_valid:
            try:
                parsed_result.graph = self._graph_builder(loaded_spec)
            except Exception as exc:  # pragma: no cover
                parsed_result.validation_errors.append(str(exc))
                parsed_result.is_valid = False

        if parsed_result.is_valid:
            parsed_result.mermaid_text = self._build_mermaid(parsed_result)

        return parsed_result

    def _parse_yaml(self, yaml_text: str) -> WorkflowDefinitionValidationResult:
        try:
            parsed = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError as exc:
            return WorkflowDefinitionValidationResult(
                is_valid=False,
                yaml_text=yaml_text,
                parse_errors=[str(exc)],
            )

        if not isinstance(parsed, dict):
            return WorkflowDefinitionValidationResult(
                is_valid=False,
                yaml_text=yaml_text,
                parse_errors=['Workflow YAML must be a mapping at the top level.'],
            )

        node_summaries = self._normalize_nodes(parsed)
        edge_summaries = self._normalize_edges(parsed)
        return WorkflowDefinitionValidationResult(
            is_valid=True,
            yaml_text=yaml_text,
            workflow_id=self._extract_workflow_id(parsed),
            workflow_name=self._extract_workflow_name(parsed),
            version=self._extract_version(parsed),
            description=self._extract_description(parsed),
            node_count=len(node_summaries),
            edge_count=len(edge_summaries),
            node_summaries=node_summaries,
            edge_summaries=edge_summaries,
            parsed_data=parsed,
        )

    def _fallback_validate(self, parsed: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        workflow_id = self._extract_workflow_id(parsed)
        if not workflow_id:
            errors.append('workflow_id (or workflow.id) is required.')

        nodes = self._normalize_nodes(parsed)
        edges = self._normalize_edges(parsed)
        node_ids = [node['node_id'] for node in nodes if node.get('node_id')]
        if not node_ids:
            errors.append('At least one node is required.')
        if len(node_ids) != len(set(node_ids)):
            errors.append('Duplicate node_id values are not allowed.')

        node_id_set = set(node_ids)
        for edge in edges:
            from_node = edge.get('from_node_id')
            to_node = edge.get('to_node_id')
            if not from_node or not to_node:
                errors.append('Each edge must define from/to (or source/target).')
                continue
            if from_node not in node_id_set:
                errors.append(f'Unknown edge source node: {from_node}')
            if to_node not in node_id_set:
                errors.append(f'Unknown edge target node: {to_node}')
        return errors

    def _build_mermaid(self, result: WorkflowDefinitionValidationResult) -> str:
        if result.graph is not None and self._mermaid_builder is not None:
            return self._mermaid_builder(result.graph)
        lines = ['graph TD']
        for node in result.node_summaries:
            node_id = str(node.get('node_id'))
            node_name = str(node.get('node_name') or node_id)
            safe_name = node_name.replace('"', "'")
            lines.append(f'    {node_id}["{safe_name}"]')
        for edge in result.edge_summaries:
            from_node = str(edge.get('from_node_id'))
            to_node = str(edge.get('to_node_id'))
            label = str(edge.get('label') or '').strip()
            if label:
                safe_label = label.replace('"', "'")
                lines.append(f'    {from_node} --|"{safe_label}"| {to_node}')
            else:
                lines.append(f'    {from_node} --> {to_node}')
        return '\n'.join(lines)

    def _normalize_nodes(self, parsed: dict[str, Any]) -> list[dict[str, Any]]:
        nodes = parsed.get('nodes')
        normalized: list[dict[str, Any]] = []
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_id = node.get('node_id') or node.get('id')
                normalized.append(
                    {
                        'node_id': str(node_id) if node_id is not None else '',
                        'node_name': str(node.get('name') or node.get('display_name') or node_id or ''),
                        'node_type': str(node.get('node_type') or node.get('type') or ''),
                        'group': node.get('group'),
                    }
                )
            return normalized
        if isinstance(nodes, dict):
            for node_id, payload in nodes.items():
                if not isinstance(payload, dict):
                    continue
                normalized.append(
                    {
                        'node_id': str(node_id),
                        'node_name': str(payload.get('name') or payload.get('display_name') or node_id),
                        'node_type': str(payload.get('node_type') or payload.get('type') or ''),
                        'group': payload.get('group'),
                    }
                )
        return normalized

    def _normalize_edges(self, parsed: dict[str, Any]) -> list[dict[str, Any]]:
        edges = parsed.get('edges')
        normalized: list[dict[str, Any]] = []
        if isinstance(edges, list):
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                normalized.append(
                    {
                        'from_node_id': str(edge.get('from') or edge.get('source') or ''),
                        'to_node_id': str(edge.get('to') or edge.get('target') or ''),
                        'label': edge.get('label') or edge.get('condition'),
                    }
                )
        return normalized

    def _extract_workflow_id(self, parsed: dict[str, Any]) -> str | None:
        if isinstance(parsed.get('workflow_id'), str):
            return parsed['workflow_id']
        workflow = parsed.get('workflow')
        if isinstance(workflow, dict) and isinstance(workflow.get('id'), str):
            return workflow['id']
        return None

    def _extract_workflow_name(self, parsed: dict[str, Any]) -> str | None:
        if isinstance(parsed.get('workflow_name'), str):
            return parsed['workflow_name']
        workflow = parsed.get('workflow')
        if isinstance(workflow, dict):
            for key in ('name', 'workflow_name', 'title'):
                if isinstance(workflow.get(key), str):
                    return str(workflow[key])
        return None

    def _extract_version(self, parsed: dict[str, Any]) -> str | None:
        if isinstance(parsed.get('version'), str):
            return parsed['version']
        workflow = parsed.get('workflow')
        if isinstance(workflow, dict) and isinstance(workflow.get('version'), str):
            return str(workflow['version'])
        return None

    def _extract_description(self, parsed: dict[str, Any]) -> str | None:
        if isinstance(parsed.get('description'), str):
            return parsed['description']
        workflow = parsed.get('workflow')
        if isinstance(workflow, dict) and isinstance(workflow.get('description'), str):
            return str(workflow['description'])
        return None
