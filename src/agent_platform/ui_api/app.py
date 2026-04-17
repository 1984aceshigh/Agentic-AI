from __future__ import annotations

from pathlib import Path
from collections.abc import MutableMapping

from flask import Flask, jsonify, render_template_string, request
from werkzeug.exceptions import HTTPException

from agent_platform.workflow_definitions import (
    DefinitionEditorService,
    DefinitionValidationService,
    FileWorkflowDefinitionRepository,
    WorkflowDefinitionService,
)
from agent_platform.runtime.execution_service import WorkflowExecutionService
from agent_platform.integrations import RAGDatasetService, RAGNodeBindingService
from agent_platform.models import GraphModel

from .action_routes import action_bp
from .api_routes import api_bp
from .definition_action_routes import definition_action_bp
from .definition_api_routes import definition_api_bp
from .definition_read_model_service import DefinitionReadModelService
from .definition_web_routes import definition_web_bp
from .dependencies import ExecutionService, HumanGateService, RerunService, register_ui_dependencies
from .read_model_service import ReadModelService
from .web_routes import web_bp


def create_app(
    read_model_service: ReadModelService,
    human_gate_service: HumanGateService,
    rerun_service: RerunService,
    execution_service: ExecutionService | None = None,
    *,
    workflow_definition_service: WorkflowDefinitionService | None = None,
    definition_editor_service: DefinitionEditorService | None = None,
    definition_validation_service: DefinitionValidationService | None = None,
    definition_read_model_service: DefinitionReadModelService | None = None,
    workflow_graphs: MutableMapping[str, GraphModel] | None = None,
    latest_execution_ids: MutableMapping[str, str | None] | None = None,
    rag_dataset_service: RAGDatasetService | None = None,
    rag_node_binding_service: RAGNodeBindingService | None = None,
) -> Flask:
    project_root = Path(__file__).resolve().parents[3]
    template_folder = project_root / 'templates'
    static_folder = project_root / 'static'
    app = Flask(
        __name__,
        template_folder=str(template_folder),
        static_folder=str(static_folder),
    )

    workflow_graphs = workflow_graphs if workflow_graphs is not None else {}
    latest_execution_ids = latest_execution_ids if latest_execution_ids is not None else {}
    rag_dataset_service = rag_dataset_service or RAGDatasetService(
        catalog_path=project_root / 'data' / 'rag' / 'datasets.json',
        datasets_dir=project_root / 'data' / 'rag' / 'datasets',
        uploads_dir=project_root / 'data' / 'rag' / 'uploads',
    )
    rag_node_binding_service = rag_node_binding_service or RAGNodeBindingService(
        bindings_path=project_root / 'data' / 'rag' / 'node_bindings.json',
    )
    definition_validation_service = definition_validation_service or DefinitionValidationService()
    definition_editor_service = definition_editor_service or DefinitionEditorService()
    workflow_definition_service = workflow_definition_service or WorkflowDefinitionService(
        FileWorkflowDefinitionRepository(project_root / 'data' / 'workflow_definitions'),
        definition_validation_service,
        workflow_graphs=workflow_graphs,
        latest_execution_ids=latest_execution_ids,
    )
    definition_read_model_service = definition_read_model_service or DefinitionReadModelService(
        workflow_definition_service,
        definition_validation_service,
        rag_dataset_service=rag_dataset_service,
        rag_node_binding_service=rag_node_binding_service,
    )

    if execution_service is None:
        context_manager = getattr(read_model_service, "_context_manager", None)
        records_manager = getattr(read_model_service, "_records_manager", None)
        if context_manager is not None and records_manager is not None:
            execution_service = WorkflowExecutionService(
                context_manager=context_manager,
                records_manager=records_manager,
                workflow_graphs=workflow_graphs,
                latest_execution_ids=latest_execution_ids,
                rag_dataset_service=rag_dataset_service,
                rag_node_binding_service=rag_node_binding_service,
            )

    register_ui_dependencies(
        app,
        read_model_service=read_model_service,
        human_gate_service=human_gate_service,
        rerun_service=rerun_service,
        execution_service=execution_service,
        workflow_graphs=workflow_graphs,
        latest_execution_ids=latest_execution_ids,
        workflow_definition_service=workflow_definition_service,
        definition_editor_service=definition_editor_service,
        definition_validation_service=definition_validation_service,
        definition_read_model_service=definition_read_model_service,
        rag_dataset_service=rag_dataset_service,
        rag_node_binding_service=rag_node_binding_service,
    )

    app.register_blueprint(web_bp)
    app.register_blueprint(action_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(definition_web_bp)
    app.register_blueprint(definition_action_bp)
    app.register_blueprint(definition_api_bp)

    @app.errorhandler(404)
    def handle_not_found(error: HTTPException):
        return _render_error(error, status_code=404)

    @app.errorhandler(400)
    def handle_bad_request(error: HTTPException):
        return _render_error(error, status_code=400)

    @app.errorhandler(KeyError)
    def handle_key_error(error: KeyError):
        message = str(error)
        if _wants_json_response():
            return jsonify({'status': 'error', 'code': 404, 'message': message}), 404
        return render_template_string(
            '<h1>404 Not Found</h1><p>{{ message }}</p>',
            message=message,
        ), 404

    return app


def _render_error(error: HTTPException, status_code: int):
    message = error.description if getattr(error, 'description', None) else error.name
    if _wants_json_response():
        return jsonify({'status': 'error', 'code': status_code, 'message': message}), status_code
    return render_template_string(
        '<h1>{{ title }}</h1><p>{{ message }}</p>',
        title=f'{status_code} {error.name}',
        message=message,
    ), status_code


def _wants_json_response() -> bool:
    path = request.path
    return path.startswith('/api/') or path.startswith('/actions/')
