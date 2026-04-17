from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class WorkflowDefinitionMeta:
    workflow_id: str
    workflow_name: str
    version: str | None
    description: str | None
    updated_at: str | None
    is_archived: bool
    validation_status: str | None = None
    node_count: int | None = None
    edge_count: int | None = None
    source_path: str | None = None


@dataclass(slots=True)
class WorkflowDefinitionDocument:
    workflow_id: str
    workflow_name: str
    version: str | None
    description: str | None
    yaml_text: str
    updated_at: str | None
    is_archived: bool
    source_path: str | None = None


class WorkflowDefinitionRepository(Protocol):
    def list_active(self) -> list[WorkflowDefinitionMeta]: ...

    def list_archived(self) -> list[WorkflowDefinitionMeta]: ...

    def get(self, workflow_id: str, *, include_archived: bool = False) -> WorkflowDefinitionDocument: ...

    def save(self, document: WorkflowDefinitionDocument) -> WorkflowDefinitionDocument: ...

    def archive(self, workflow_id: str) -> WorkflowDefinitionDocument: ...

    def clone(self, source_workflow_id: str, *, new_workflow_id: str | None = None) -> WorkflowDefinitionDocument: ...

    def delete(self, workflow_id: str, *, include_archived: bool = False) -> bool: ...
