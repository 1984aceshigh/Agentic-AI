from __future__ import annotations

from typing import Any, MutableMapping

import yaml

from .definition_validation_service import DefinitionValidationService, WorkflowDefinitionValidationResult
from .repository import WorkflowDefinitionDocument, WorkflowDefinitionMeta, WorkflowDefinitionRepository


class WorkflowDefinitionService:
    def __init__(
        self,
        repository: WorkflowDefinitionRepository,
        validation_service: DefinitionValidationService,
        *,
        workflow_graphs: MutableMapping[str, Any] | None = None,
        latest_execution_ids: MutableMapping[str, str | None] | None = None,
    ) -> None:
        self._repository = repository
        self._validation_service = validation_service
        self._workflow_graphs = workflow_graphs if workflow_graphs is not None else {}
        self._latest_execution_ids = latest_execution_ids if latest_execution_ids is not None else {}

    @property
    def repository(self) -> WorkflowDefinitionRepository:
        return self._repository

    def list_definitions(self, *, include_archived: bool = False) -> list[WorkflowDefinitionMeta]:
        active_items = self._repository.list_active()
        if not include_archived:
            return active_items
        return active_items + self._repository.list_archived()

    def get_definition(self, workflow_id: str, *, include_archived: bool = False) -> WorkflowDefinitionDocument:
        return self._repository.get(workflow_id, include_archived=include_archived)

    def create_empty_definition(self, workflow_id: str = 'new_workflow') -> WorkflowDefinitionDocument:
        skeleton = {
            'workflow_id': workflow_id,
            'workflow_name': workflow_id,
            'version': '0.1.0',
            'nodes': [
                {'id': 'start_node', 'name': 'Start Node', 'type': 'llm_generate'},
                {'id': 'end_node', 'name': 'End Node', 'type': 'deterministic_transform'},
            ],
            'edges': [{'from': 'start_node', 'to': 'end_node'}],
        }
        yaml_text = yaml.safe_dump(skeleton, allow_unicode=True, sort_keys=False)
        return WorkflowDefinitionDocument(
            workflow_id=workflow_id,
            workflow_name=workflow_id,
            version='0.1.0',
            description=None,
            yaml_text=yaml_text,
            updated_at=None,
            is_archived=False,
            source_path=None,
        )

    def validate_yaml_text(self, yaml_text: str) -> WorkflowDefinitionValidationResult:
        return self._validation_service.validate_yaml_text(yaml_text)

    def save_definition(self, yaml_text: str, *, workflow_id: str | None = None) -> tuple[WorkflowDefinitionDocument, WorkflowDefinitionValidationResult]:
        validation = self._validation_service.validate_yaml_text(yaml_text)
        if not validation.is_valid:
            raise ValueError('Cannot save invalid workflow definition.')
        resolved_workflow_id = workflow_id or validation.workflow_id
        if not resolved_workflow_id:
            raise ValueError('workflow_id could not be determined.')
        document = WorkflowDefinitionDocument(
            workflow_id=resolved_workflow_id,
            workflow_name=validation.workflow_name or resolved_workflow_id,
            version=validation.version,
            description=validation.description,
            yaml_text=yaml_text,
            updated_at=None,
            is_archived=False,
            source_path=None,
        )
        saved = self._repository.save(document)
        if validation.graph is not None:
            self._workflow_graphs[resolved_workflow_id] = validation.graph
        self._latest_execution_ids.setdefault(resolved_workflow_id, None)
        return saved, validation

    def clone_definition(self, source_workflow_id: str, *, new_workflow_id: str | None = None) -> WorkflowDefinitionDocument:
        cloned = self._repository.clone(source_workflow_id, new_workflow_id=new_workflow_id)
        validation = self._validation_service.validate_yaml_text(cloned.yaml_text)
        if validation.graph is not None:
            self._workflow_graphs[cloned.workflow_id] = validation.graph
        self._latest_execution_ids.setdefault(cloned.workflow_id, None)
        return cloned

    def archive_definition(self, workflow_id: str) -> WorkflowDefinitionDocument:
        archived = self._repository.archive(workflow_id)
        self._workflow_graphs.pop(workflow_id, None)
        self._latest_execution_ids.pop(workflow_id, None)
        return archived
