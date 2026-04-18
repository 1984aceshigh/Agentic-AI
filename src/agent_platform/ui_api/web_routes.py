from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from .dependencies import (
    get_latest_execution_ids,
    get_read_model_service,
    get_workflow_graphs,
)

web_bp = Blueprint("web_routes", __name__)
_ALLOWED_STATUSES = {"FAILED", "WAITING_HUMAN", "RUNNING", "SUCCEEDED", "PENDING", "SKIPPED"}


@web_bp.get("/workflows")
def workflows() -> str:
    read_model_service = get_read_model_service()
    workflow_graphs = get_workflow_graphs()
    latest_execution_ids = get_latest_execution_ids()

    summaries = []
    for workflow_id, graph in workflow_graphs.items():
        execution_id = latest_execution_ids.get(workflow_id)
        summaries.append(read_model_service.build_workflow_summary(graph, execution_id))

    return render_template("workflows.html", workflow_summaries=summaries)


@web_bp.get("/executions")
def execution_list() -> str:
    read_model_service = get_read_model_service()
    selected_workflow_id = request.args.get("workflow_id")
    workflow_id = selected_workflow_id.strip() if isinstance(selected_workflow_id, str) and selected_workflow_id.strip() else None
    execution_summaries = read_model_service.build_execution_summaries(workflow_id=workflow_id)

    return render_template(
        "execution_list.html",
        execution_summaries=execution_summaries,
        selected_workflow_id=workflow_id,
    )


@web_bp.get("/executions/<execution_id>")
def execution_detail(execution_id: str) -> str:
    read_model_service = get_read_model_service()
    try:
        execution_detail_view = read_model_service.build_execution_detail(execution_id)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    return render_template(
        "execution_detail.html",
        execution=execution_detail_view,
    )


@web_bp.get("/workflows/<workflow_id>/executions/<execution_id>/nodes")
def node_list(workflow_id: str, execution_id: str) -> str:
    return _render_node_list(workflow_id=workflow_id, execution_id=execution_id)


@web_bp.get("/workflows/<workflow_id>/nodes")
def node_list_latest(workflow_id: str) -> str:
    latest_execution_ids = get_latest_execution_ids()
    execution_id = latest_execution_ids.get(workflow_id)
    return _render_node_list(workflow_id=workflow_id, execution_id=execution_id)


def _render_node_list(workflow_id: str, execution_id: str | None) -> str:
    graph = _get_graph_or_404(workflow_id)
    read_model_service = get_read_model_service()
    try:
        node_cards = read_model_service.build_node_cards(graph, execution_id)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    selected_status = _normalize_status_filter(request.args.get("status"))
    visible_node_cards = _filter_node_cards(node_cards, selected_status)

    return render_template(
        "node_list.html",
        workflow_id=workflow_id,
        execution_id=execution_id,
        has_execution=execution_id is not None,
        node_list_path=_build_node_list_path(workflow_id, execution_id),
        workflow_name=graph.workflow_name,
        node_cards=visible_node_cards,
        total_node_count=len(node_cards),
        visible_node_count=len(visible_node_cards),
        selected_status=selected_status,
        available_statuses=sorted(_ALLOWED_STATUSES),
    )


@web_bp.get("/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>")
def node_detail(workflow_id: str, execution_id: str, node_id: str) -> str:
    graph = _get_graph_or_404(workflow_id)
    read_model_service = get_read_model_service()
    try:
        node_detail_view = read_model_service.build_node_detail(graph, execution_id, node_id)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    return render_template(
        "node_detail.html",
        workflow_id=workflow_id,
        execution_id=execution_id,
        node_list_path=_build_node_list_path(workflow_id, execution_id),
        workflow_name=graph.workflow_name,
        node=node_detail_view,
    )


@web_bp.get("/workflows/<workflow_id>/graph")
def graph_view(workflow_id: str) -> str:
    graph = _get_graph_or_404(workflow_id)
    read_model_service = get_read_model_service()
    latest_execution_ids = get_latest_execution_ids()
    graph_view_model = read_model_service.build_graph_view(graph)
    return render_template(
        "graph_view.html",
        workflow_id=workflow_id,
        graph_view=graph_view_model,
        latest_execution_id=latest_execution_ids.get(workflow_id),
    )


def _get_graph_or_404(workflow_id: str):
    workflow_graphs = get_workflow_graphs()
    graph = workflow_graphs.get(workflow_id)
    if graph is None:
        abort(404, description=f"Unknown workflow_id: {workflow_id}")
    return graph


def _normalize_status_filter(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().upper()
    if not candidate or candidate == "ALL":
        return None
    if candidate not in _ALLOWED_STATUSES:
        return None
    return candidate


def _filter_node_cards(node_cards, selected_status: str | None):
    if selected_status is None:
        return node_cards
    return [card for card in node_cards if card.status == selected_status]


def _build_node_list_path(workflow_id: str, execution_id: str | None) -> str:
    if execution_id is None:
        return f"/workflows/{workflow_id}/nodes"
    return f"/workflows/{workflow_id}/executions/{execution_id}/nodes"
