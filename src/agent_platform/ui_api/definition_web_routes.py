from __future__ import annotations

from flask import Blueprint, render_template, request

from .dependencies import get_definition_read_model_service


definition_web_bp = Blueprint('definition_web_routes', __name__)
_ALLOWED_TABS = {'overview', 'nodes', 'edges', 'yaml', 'validation'}


@definition_web_bp.get('/workflow-definitions')
def workflow_definitions() -> str:
    include_archived = _truthy(request.args.get('include_archived'))
    summaries = get_definition_read_model_service().build_definition_summaries(include_archived=include_archived)
    return render_template(
        'workflow_definitions.html',
        definition_summaries=summaries,
        include_archived=include_archived,
    )


@definition_web_bp.get('/workflow-definitions/new')
def new_workflow_definition() -> str:
    selected_tab = _normalize_tab(request.args.get('tab'))
    selected_node_id = _optional_text(request.args.get('selected_node_id'))
    view = get_definition_read_model_service().build_graph_editor_view(
        workflow_id=None,
        selected_node_id=selected_node_id,
        selected_tab=selected_tab,
    )
    return render_template('graph_editor.html', editor=view)


@definition_web_bp.get('/workflow-definitions/<workflow_id>/edit')
def edit_workflow_definition(workflow_id: str) -> str:
    selected_tab = _normalize_tab(request.args.get('tab'))
    selected_node_id = _optional_text(request.args.get('selected_node_id'))
    view = get_definition_read_model_service().build_graph_editor_view(
        workflow_id=workflow_id,
        selected_node_id=selected_node_id,
        selected_tab=selected_tab,
    )
    return render_template('graph_editor.html', editor=view)


@definition_web_bp.get('/workflow-definitions/<workflow_id>/graph-editor')
def graph_editor(workflow_id: str) -> str:
    selected_tab = _normalize_tab(request.args.get('tab'))
    selected_node_id = _optional_text(request.args.get('selected_node_id'))
    view = get_definition_read_model_service().build_graph_editor_view(
        workflow_id=workflow_id,
        selected_node_id=selected_node_id,
        selected_tab=selected_tab,
    )
    return render_template('graph_editor.html', editor=view)


def _normalize_tab(value: str | None) -> str:
    candidate = (value or 'overview').strip().lower()
    if candidate not in _ALLOWED_TABS:
        return 'overview'
    return candidate


def _truthy(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
