from __future__ import annotations

from flask import Blueprint, abort, jsonify

from .dependencies import (
    get_latest_execution_ids,
    get_read_model_service,
    get_workflow_graphs,
)

api_bp = Blueprint("api_routes", __name__, url_prefix="/api")


@api_bp.get("/workflows")
def list_workflows():
    read_model_service = get_read_model_service()
    workflow_graphs = get_workflow_graphs()
    latest_execution_ids = get_latest_execution_ids()

    payload = []
    for workflow_id, graph in workflow_graphs.items():
        execution_id = latest_execution_ids.get(workflow_id)
        summary = read_model_service.build_workflow_summary(graph, execution_id)
        payload.append(summary.model_dump(mode="json"))
    return jsonify(payload)


@api_bp.get("/workflows/<workflow_id>/executions/<execution_id>/nodes")
def list_nodes(workflow_id: str, execution_id: str):
    workflow_graphs = get_workflow_graphs()
    graph = workflow_graphs.get(workflow_id)
    if graph is None:
        abort(404, description=f"Unknown workflow_id: {workflow_id}")

    read_model_service = get_read_model_service()
    try:
        cards = read_model_service.build_node_cards(graph, execution_id)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    return jsonify([card.model_dump(mode="json") for card in cards])
