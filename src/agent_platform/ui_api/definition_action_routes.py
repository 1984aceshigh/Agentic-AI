from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from flask import Blueprint, abort, jsonify, redirect, render_template, request

from .dependencies import (
    get_definition_editor_service,
    get_definition_read_model_service,
    get_workflow_definition_service,
)


definition_action_bp = Blueprint('definition_action_routes', __name__, url_prefix='/actions/workflow-definitions')


@definition_action_bp.post('/validate')
def validate_definition():
    payload = _get_payload()
    yaml_text = _required_str(payload.get('yaml_text'), 'yaml_text')
    selected_tab = _optional_str(payload.get('selected_tab')) or 'validation'
    selected_node_id = _optional_str(payload.get('selected_node_id'))
    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response
    editor = get_definition_read_model_service().build_graph_editor_view(
        yaml_text=yaml_text,
        selected_node_id=selected_node_id,
        selected_tab=selected_tab,
        is_dirty=True,
    )
    if request.is_json:
        return jsonify(editor.model_dump(mode='json'))
    return render_template('graph_editor.html', editor=editor)


@definition_action_bp.post('/create')
def create_definition():
    payload = _get_payload()
    yaml_text = _required_str(payload.get('yaml_text'), 'yaml_text')
    service = get_workflow_definition_service()
    try:
        saved, validation = service.save_definition(yaml_text)
    except ValueError as exc:
        editor = get_definition_read_model_service().build_graph_editor_view(
            yaml_text=yaml_text,
            selected_node_id=_optional_str(payload.get('selected_node_id')),
            selected_tab='overview',
            is_dirty=True,
        )
        if request.is_json:
            return jsonify({'status': 'error', 'message': str(exc), 'validation_errors': editor.validation_errors}), 400
        return render_template('graph_editor.html', editor=editor), 400
    next_url = _optional_str(payload.get('next')) or f'/workflow-definitions/{saved.workflow_id}/graph-editor'
    if request.is_json:
        return jsonify({'status': 'ok', 'workflow_id': saved.workflow_id, 'validation_status': 'valid' if validation.is_valid else 'invalid'})
    return redirect(_validate_relative_path(next_url))


@definition_action_bp.post('/<workflow_id>/save')
def save_definition(workflow_id: str):
    payload = _get_payload()
    yaml_text = _required_str(payload.get('yaml_text'), 'yaml_text')
    service = get_workflow_definition_service()
    try:
        saved, validation = service.save_definition(yaml_text, workflow_id=workflow_id)
    except ValueError as exc:
        editor = get_definition_read_model_service().build_graph_editor_view(
            yaml_text=yaml_text,
            selected_node_id=_optional_str(payload.get('selected_node_id')),
            selected_tab='yaml',
            is_dirty=True,
        )
        if request.is_json:
            return jsonify({'status': 'error', 'message': str(exc), 'validation_errors': editor.validation_errors}), 400
        return render_template('graph_editor.html', editor=editor), 400
    next_url = _optional_str(payload.get('next')) or f'/workflow-definitions/{saved.workflow_id}/graph-editor'
    if request.is_json:
        return jsonify({'status': 'ok', 'workflow_id': saved.workflow_id, 'validation_status': 'valid' if validation.is_valid else 'invalid'})
    return redirect(_validate_relative_path(next_url))


@definition_action_bp.post('/<workflow_id>/clone')
def clone_definition(workflow_id: str):
    payload = _get_payload()
    new_workflow_id = _optional_str(payload.get('new_workflow_id'))
    cloned = get_workflow_definition_service().clone_definition(workflow_id, new_workflow_id=new_workflow_id)
    if request.is_json:
        return jsonify({'status': 'ok', 'workflow_id': cloned.workflow_id, 'action': 'clone'})
    return redirect(f'/workflow-definitions/{cloned.workflow_id}/graph-editor')


@definition_action_bp.post('/<workflow_id>/archive')
def archive_definition(workflow_id: str):
    archived = get_workflow_definition_service().archive_definition(workflow_id)
    if request.is_json:
        return jsonify({'status': 'ok', 'workflow_id': archived.workflow_id, 'action': 'archive'})
    return redirect('/workflow-definitions')


@definition_action_bp.post('/<workflow_id>/graph/add-node')
def add_node(workflow_id: str):
    payload = _get_payload()
    updated_yaml = get_definition_editor_service().add_node(
        _required_str(payload.get('yaml_text'), 'yaml_text'),
        {
            'node_id': payload.get('node_id'),
            'node_name': payload.get('node_name'),
            'node_type': payload.get('node_type'),
            'group': payload.get('group'),
            'advanced_yaml_fragment': payload.get('advanced_yaml_fragment'),
        },
    )
    return _render_editor_response(
        workflow_id=workflow_id,
        yaml_text=updated_yaml,
        selected_node_id=_optional_str(payload.get('node_id')),
        selected_tab='nodes',
    )


@definition_action_bp.post('/<workflow_id>/graph/update-node/<node_id>')
def update_node(workflow_id: str, node_id: str):
    payload = _get_payload()
    updated_yaml = get_definition_editor_service().update_node(
        _required_str(payload.get('yaml_text'), 'yaml_text'),
        node_id,
        {
            'node_id': payload.get('node_id'),
            'node_name': payload.get('node_name'),
            'node_type': payload.get('node_type'),
            'group': payload.get('group'),
            'advanced_yaml_fragment': payload.get('advanced_yaml_fragment'),
        },
    )
    selected_node_id = _optional_str(payload.get('node_id')) or node_id
    return _render_editor_response(
        workflow_id=workflow_id,
        yaml_text=updated_yaml,
        selected_node_id=selected_node_id,
        selected_tab='nodes',
    )


@definition_action_bp.post('/<workflow_id>/graph/delete-node/<node_id>')
def delete_node(workflow_id: str, node_id: str):
    payload = _get_payload()
    yaml_text = _required_str(payload.get('yaml_text'), 'yaml_text')
    try:
        updated_yaml = get_definition_editor_service().delete_node(yaml_text, node_id)
    except ValueError as exc:
        editor = get_definition_read_model_service().build_graph_editor_view(
            yaml_text=yaml_text,
            selected_node_id=node_id,
            selected_tab='nodes',
            is_dirty=True,
        )
        editor.validation_errors.append(str(exc))
        editor.validation_status = 'invalid'
        if request.is_json:
            return jsonify(editor.model_dump(mode='json')), 400
        return render_template('graph_editor.html', editor=editor), 400
    return _render_editor_response(
        workflow_id=workflow_id,
        yaml_text=updated_yaml,
        selected_node_id=None,
        selected_tab='nodes',
    )


@definition_action_bp.post('/<workflow_id>/graph/add-edge')
def add_edge(workflow_id: str):
    payload = _get_payload()
    updated_yaml = get_definition_editor_service().add_edge(
        _required_str(payload.get('yaml_text'), 'yaml_text'),
        _required_str(payload.get('from_node_id'), 'from_node_id'),
        _required_str(payload.get('to_node_id'), 'to_node_id'),
        {'label': payload.get('label'), 'advanced_yaml_fragment': payload.get('advanced_yaml_fragment')},
    )
    return _render_editor_response(
        workflow_id=workflow_id,
        yaml_text=updated_yaml,
        selected_node_id=_optional_str(payload.get('selected_node_id')),
        selected_tab='edges',
    )


@definition_action_bp.post('/<workflow_id>/graph/delete-edge')
def delete_edge(workflow_id: str):
    payload = _get_payload()
    updated_yaml = get_definition_editor_service().delete_edge(
        _required_str(payload.get('yaml_text'), 'yaml_text'),
        _required_str(payload.get('from_node_id'), 'from_node_id'),
        _required_str(payload.get('to_node_id'), 'to_node_id'),
    )
    return _render_editor_response(
        workflow_id=workflow_id,
        yaml_text=updated_yaml,
        selected_node_id=_optional_str(payload.get('selected_node_id')),
        selected_tab='edges',
    )


def _render_editor_response(
    *,
    workflow_id: str,
    yaml_text: str,
    selected_node_id: str | None,
    selected_tab: str,
):
    editor = get_definition_read_model_service().build_graph_editor_view(
        workflow_id=workflow_id,
        yaml_text=yaml_text,
        selected_node_id=selected_node_id,
        selected_tab=selected_tab,
        is_dirty=True,
    )
    if request.is_json:
        return jsonify(editor.model_dump(mode='json'))
    return render_template('graph_editor.html', editor=editor)


def _get_payload() -> dict[str, Any]:
    if request.is_json:
        return dict(request.get_json(silent=True) or {})
    return request.form.to_dict(flat=True)


def _required_str(value: Any, field_name: str) -> str:
    text = _optional_str(value)
    if text is None:
        abort(400, description=f'{field_name} is required.')
    return text


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _maybe_redirect(payload: dict[str, Any]):
    next_url = _optional_str(payload.get('next'))
    if next_url is None or request.is_json:
        return None
    return redirect(_validate_relative_path(next_url))


def _validate_relative_path(next_url: str) -> str:
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        abort(400, description='next must be a relative path.')
    if not next_url.startswith('/'):
        abort(400, description="next must start with '/'.")
    return next_url
