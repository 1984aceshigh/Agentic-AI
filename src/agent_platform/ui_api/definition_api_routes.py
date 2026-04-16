from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from .dependencies import get_definition_read_model_service, get_workflow_definition_service


definition_api_bp = Blueprint('definition_api_routes', __name__, url_prefix='/api/workflow-definitions')


@definition_api_bp.get('')
def list_definitions():
    include_archived = str(request.args.get('include_archived') or '').strip().lower() in {'1', 'true', 'yes'}
    summaries = get_definition_read_model_service().build_definition_summaries(include_archived=include_archived)
    return jsonify([item.model_dump(mode='json') for item in summaries])


@definition_api_bp.get('/<workflow_id>')
def get_definition(workflow_id: str):
    try:
        document = get_workflow_definition_service().get_definition(workflow_id, include_archived=True)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc
    return jsonify(
        {
            'workflow_id': document.workflow_id,
            'workflow_name': document.workflow_name,
            'version': document.version,
            'description': document.description,
            'yaml_text': document.yaml_text,
            'updated_at': document.updated_at,
            'is_archived': document.is_archived,
        }
    )


@definition_api_bp.post('/validate')
def validate_definition():
    payload = request.get_json(silent=True) or {}
    yaml_text = str(payload.get('yaml_text') or '')
    if not yaml_text.strip():
        abort(400, description='yaml_text is required.')
    result = get_workflow_definition_service().validate_yaml_text(yaml_text)
    return jsonify(
        {
            'is_valid': result.is_valid,
            'workflow_id': result.workflow_id,
            'workflow_name': result.workflow_name,
            'version': result.version,
            'parse_errors': result.parse_errors,
            'validation_errors': result.validation_errors,
            'warnings': result.warnings,
            'node_count': result.node_count,
            'edge_count': result.edge_count,
            'mermaid_text': result.mermaid_text,
            'node_summaries': result.node_summaries,
            'edge_summaries': result.edge_summaries,
        }
    )


@definition_api_bp.get('/<workflow_id>/graph-editor-state')
def graph_editor_state(workflow_id: str):
    selected_node_id = request.args.get('selected_node_id') or None
    selected_tab = request.args.get('tab') or 'nodes'
    editor = get_definition_read_model_service().build_graph_editor_view(
        workflow_id=workflow_id,
        selected_node_id=selected_node_id,
        selected_tab=selected_tab,
    )
    return jsonify(editor.model_dump(mode='json'))
