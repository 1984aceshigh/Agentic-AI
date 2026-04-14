from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Protocol, cast

from flask import Flask, current_app

from agent_platform.models import GraphModel
from agent_platform.workflow_definitions import (
    DefinitionEditorService,
    DefinitionValidationService,
    WorkflowDefinitionService,
)

from .definition_read_model_service import DefinitionReadModelService
from .read_model_service import ReadModelService

_UI_DEPENDENCY_KEY = 'agent_platform_ui_dependencies'


class HumanGateService(Protocol):
    def approve_node(
        self,
        execution_id: str,
        node_id: str,
        comment: str | None = None,
    ) -> None: ...

    def reject_node(
        self,
        execution_id: str,
        node_id: str,
        fallback_node_id: str | None = None,
        comment: str | None = None,
    ) -> None: ...


class RerunService(Protocol):
    def rerun_from_node(
        self,
        execution_id: str,
        from_node_id: str,
    ) -> None: ...


class UIDependencyContainer(dict):
    pass


def register_ui_dependencies(
    app: Flask,
    read_model_service: ReadModelService,
    human_gate_service: HumanGateService,
    rerun_service: RerunService,
    *,
    workflow_graphs: MutableMapping[str, GraphModel] | None = None,
    latest_execution_ids: MutableMapping[str, str | None] | None = None,
    workflow_definition_service: WorkflowDefinitionService | None = None,
    definition_editor_service: DefinitionEditorService | None = None,
    definition_validation_service: DefinitionValidationService | None = None,
    definition_read_model_service: DefinitionReadModelService | None = None,
) -> None:
    app.extensions[_UI_DEPENDENCY_KEY] = UIDependencyContainer(
        read_model_service=read_model_service,
        human_gate_service=human_gate_service,
        rerun_service=rerun_service,
        workflow_graphs=workflow_graphs if workflow_graphs is not None else {},
        latest_execution_ids=latest_execution_ids if latest_execution_ids is not None else {},
        workflow_definition_service=workflow_definition_service,
        definition_editor_service=definition_editor_service,
        definition_validation_service=definition_validation_service,
        definition_read_model_service=definition_read_model_service,
    )


def get_dependency_container() -> UIDependencyContainer:
    container = current_app.extensions.get(_UI_DEPENDENCY_KEY)
    if container is None:
        raise RuntimeError('UI dependencies are not registered.')
    return cast(UIDependencyContainer, container)


def get_read_model_service() -> ReadModelService:
    return cast(ReadModelService, get_dependency_container()['read_model_service'])


def get_human_gate_service() -> HumanGateService:
    return cast(HumanGateService, get_dependency_container()['human_gate_service'])


def get_rerun_service() -> RerunService:
    return cast(RerunService, get_dependency_container()['rerun_service'])


def get_workflow_graphs() -> MutableMapping[str, GraphModel]:
    return cast(MutableMapping[str, GraphModel], get_dependency_container()['workflow_graphs'])


def get_latest_execution_ids() -> MutableMapping[str, str | None]:
    return cast(MutableMapping[str, str | None], get_dependency_container()['latest_execution_ids'])


def get_workflow_definition_service() -> WorkflowDefinitionService:
    service = get_dependency_container().get('workflow_definition_service')
    if service is None:
        raise RuntimeError('WorkflowDefinitionService is not registered.')
    return cast(WorkflowDefinitionService, service)


def get_definition_editor_service() -> DefinitionEditorService:
    service = get_dependency_container().get('definition_editor_service')
    if service is None:
        raise RuntimeError('DefinitionEditorService is not registered.')
    return cast(DefinitionEditorService, service)


def get_definition_validation_service() -> DefinitionValidationService:
    service = get_dependency_container().get('definition_validation_service')
    if service is None:
        raise RuntimeError('DefinitionValidationService is not registered.')
    return cast(DefinitionValidationService, service)


def get_definition_read_model_service() -> DefinitionReadModelService:
    service = get_dependency_container().get('definition_read_model_service')
    if service is None:
        raise RuntimeError('DefinitionReadModelService is not registered.')
    return cast(DefinitionReadModelService, service)


def set_workflow_graphs(app: Flask, workflow_graphs: Mapping[str, GraphModel]) -> None:
    container = cast(UIDependencyContainer, app.extensions[_UI_DEPENDENCY_KEY])
    container['workflow_graphs'] = dict(workflow_graphs)


def set_latest_execution_ids(app: Flask, latest_execution_ids: Mapping[str, str | None]) -> None:
    container = cast(UIDependencyContainer, app.extensions[_UI_DEPENDENCY_KEY])
    container['latest_execution_ids'] = dict(latest_execution_ids)
