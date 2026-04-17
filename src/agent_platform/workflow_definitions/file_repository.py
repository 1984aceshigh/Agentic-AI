from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .repository import WorkflowDefinitionDocument, WorkflowDefinitionMeta, WorkflowDefinitionRepository


class FileWorkflowDefinitionRepository(WorkflowDefinitionRepository):
    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)
        self._active_dir = self._root_dir / 'active'
        self._archived_dir = self._root_dir / 'archived'
        self._active_dir.mkdir(parents=True, exist_ok=True)
        self._archived_dir.mkdir(parents=True, exist_ok=True)

    def list_active(self) -> list[WorkflowDefinitionMeta]:
        return self._list_from_dir(self._active_dir, is_archived=False)

    def list_archived(self) -> list[WorkflowDefinitionMeta]:
        return self._list_from_dir(self._archived_dir, is_archived=True)

    def get(self, workflow_id: str, *, include_archived: bool = False) -> WorkflowDefinitionDocument:
        active_path = self._active_dir / f'{workflow_id}.yaml'
        if active_path.exists():
            return self._read_document(active_path, is_archived=False)
        if include_archived:
            archived_matches = sorted(self._archived_dir.glob(f'{workflow_id}__*.yaml'))
            if archived_matches:
                return self._read_document(archived_matches[-1], is_archived=True)
        raise KeyError(f'Unknown workflow definition: {workflow_id}')

    def save(self, document: WorkflowDefinitionDocument) -> WorkflowDefinitionDocument:
        path = self._active_dir / f'{document.workflow_id}.yaml'
        path.write_text(document.yaml_text, encoding='utf-8')
        return self._read_document(path, is_archived=False)

    def archive(self, workflow_id: str) -> WorkflowDefinitionDocument:
        source = self._active_dir / f'{workflow_id}.yaml'
        if not source.exists():
            raise KeyError(f'Unknown workflow definition: {workflow_id}')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        destination = self._archived_dir / f'{workflow_id}__{stamp}.yaml'
        destination.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
        source.unlink()
        return self._read_document(destination, is_archived=True)

    def clone(self, source_workflow_id: str, *, new_workflow_id: str | None = None) -> WorkflowDefinitionDocument:
        source = self.get(source_workflow_id, include_archived=True)
        parsed = _safe_load_yaml(source.yaml_text)
        cloned_workflow_id = new_workflow_id or f'{source.workflow_id}_copy'
        updated = _replace_workflow_identity(parsed, cloned_workflow_id)
        yaml_text = yaml.safe_dump(updated, allow_unicode=True, sort_keys=False)
        document = WorkflowDefinitionDocument(
            workflow_id=cloned_workflow_id,
            workflow_name=_extract_workflow_name(updated) or f'{source.workflow_name} Copy',
            version=_extract_version(updated),
            description=_extract_description(updated),
            yaml_text=yaml_text,
            updated_at=None,
            is_archived=False,
            source_path=None,
        )
        return self.save(document)

    def delete(self, workflow_id: str, *, include_archived: bool = False) -> bool:
        deleted = False
        active_path = self._active_dir / f'{workflow_id}.yaml'
        if active_path.exists():
            active_path.unlink()
            deleted = True

        if include_archived:
            archived_matches = list(self._archived_dir.glob(f'{workflow_id}__*.yaml'))
            for path in archived_matches:
                path.unlink()
                deleted = True

        return deleted

    def _list_from_dir(self, directory: Path, *, is_archived: bool) -> list[WorkflowDefinitionMeta]:
        items: list[WorkflowDefinitionMeta] = []
        for path in sorted(directory.glob('*.yaml')):
            items.append(self._read_meta(path, is_archived=is_archived))
        items.sort(key=lambda item: item.updated_at or '', reverse=True)
        return items

    def _read_meta(self, path: Path, *, is_archived: bool) -> WorkflowDefinitionMeta:
        data = _safe_load_yaml(path.read_text(encoding='utf-8'))
        workflow_id = _extract_workflow_id(data) or path.stem.split('__', 1)[0]
        return WorkflowDefinitionMeta(
            workflow_id=workflow_id,
            workflow_name=_extract_workflow_name(data) or workflow_id,
            version=_extract_version(data),
            description=_extract_description(data),
            updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            is_archived=is_archived,
            node_count=len(_normalize_nodes(data)),
            edge_count=len(_normalize_edges(data)),
            source_path=str(path),
        )

    def _read_document(self, path: Path, *, is_archived: bool) -> WorkflowDefinitionDocument:
        yaml_text = path.read_text(encoding='utf-8')
        data = _safe_load_yaml(yaml_text)
        workflow_id = _extract_workflow_id(data) or path.stem.split('__', 1)[0]
        return WorkflowDefinitionDocument(
            workflow_id=workflow_id,
            workflow_name=_extract_workflow_name(data) or workflow_id,
            version=_extract_version(data),
            description=_extract_description(data),
            yaml_text=yaml_text,
            updated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            is_archived=is_archived,
            source_path=str(path),
        )


def _safe_load_yaml(yaml_text: str) -> dict[str, Any]:
    loaded = yaml.safe_load(yaml_text) or {}
    if not isinstance(loaded, dict):
        raise ValueError('Workflow YAML must be a mapping at the top level.')
    return loaded


def _replace_workflow_identity(data: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    updated = dict(data)
    if isinstance(updated.get('workflow'), dict):
        workflow = dict(updated['workflow'])
        workflow['id'] = workflow_id
        workflow.setdefault('name', workflow_id)
        updated['workflow'] = workflow
    else:
        updated['workflow_id'] = workflow_id
        updated.setdefault('workflow_name', workflow_id)
    return updated


def _extract_workflow_id(data: dict[str, Any]) -> str | None:
    if isinstance(data.get('workflow_id'), str):
        return str(data['workflow_id'])
    workflow = data.get('workflow')
    if isinstance(workflow, dict):
        value = workflow.get('id')
        if isinstance(value, str):
            return value
    return None


def _extract_workflow_name(data: dict[str, Any]) -> str | None:
    if isinstance(data.get('workflow_name'), str):
        return str(data['workflow_name'])
    workflow = data.get('workflow')
    if isinstance(workflow, dict):
        for key in ('name', 'workflow_name', 'title'):
            value = workflow.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _extract_version(data: dict[str, Any]) -> str | None:
    if isinstance(data.get('version'), str):
        return str(data['version'])
    workflow = data.get('workflow')
    if isinstance(workflow, dict):
        value = workflow.get('version')
        if isinstance(value, str):
            return value
    return None


def _extract_description(data: dict[str, Any]) -> str | None:
    if isinstance(data.get('description'), str):
        return str(data['description'])
    workflow = data.get('workflow')
    if isinstance(workflow, dict):
        value = workflow.get('description')
        if isinstance(value, str):
            return value
    return None


def _normalize_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = data.get('nodes')
    if isinstance(nodes, list):
        return [node for node in nodes if isinstance(node, dict)]
    if isinstance(nodes, dict):
        normalized: list[dict[str, Any]] = []
        for node_id, node_payload in nodes.items():
            if isinstance(node_payload, dict):
                item = dict(node_payload)
                item.setdefault('id', str(node_id))
                normalized.append(item)
        return normalized
    return []


def _normalize_edges(data: dict[str, Any]) -> list[dict[str, Any]]:
    edges = data.get('edges')
    if isinstance(edges, list):
        return [edge for edge in edges if isinstance(edge, dict)]
    return []
