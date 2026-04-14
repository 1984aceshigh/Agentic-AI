from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from flask import Blueprint, abort, jsonify, redirect, request

from .dependencies import (
    get_human_gate_service,
    get_rerun_service,
    get_workflow_graphs,
)

action_bp = Blueprint("action_routes", __name__, url_prefix="/actions")


@action_bp.post("/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/approve")
def approve_node(workflow_id: str, execution_id: str, node_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    comment = _optional_str(payload.get("comment"))

    human_gate_service = get_human_gate_service()
    try:
        human_gate_service.approve_node(execution_id=execution_id, node_id=node_id, comment=comment)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response

    return jsonify({"status": "ok", "action": "approve", "node_id": node_id})


@action_bp.post("/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/reject")
def reject_node(workflow_id: str, execution_id: str, node_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    fallback_node_id = _optional_str(payload.get("fallback_node_id"))
    comment = _optional_str(payload.get("comment"))

    human_gate_service = get_human_gate_service()
    try:
        human_gate_service.reject_node(
            execution_id=execution_id,
            node_id=node_id,
            fallback_node_id=fallback_node_id,
            comment=comment,
        )
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response

    return jsonify(
        {
            "status": "ok",
            "action": "reject",
            "node_id": node_id,
            "fallback_node_id": fallback_node_id,
        }
    )


@action_bp.post("/workflows/<workflow_id>/executions/<execution_id>/rerun")
def rerun_workflow(workflow_id: str, execution_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    from_node_id = _optional_str(payload.get("from_node_id"))
    if not from_node_id:
        abort(400, description="from_node_id is required.")

    rerun_service = get_rerun_service()
    try:
        rerun_service.rerun_from_node(execution_id=execution_id, from_node_id=from_node_id)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response

    return jsonify(
        {
            "status": "ok",
            "action": "rerun",
            "from_node_id": from_node_id,
        }
    )


def _ensure_workflow_exists(workflow_id: str) -> None:
    if workflow_id not in get_workflow_graphs():
        abort(404, description=f"Unknown workflow_id: {workflow_id}")


def _get_payload() -> dict[str, Any]:
    if request.is_json:
        return dict(request.get_json(silent=True) or {})
    return request.form.to_dict(flat=True)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _maybe_redirect(payload: dict[str, Any]):
    next_url = _optional_str(payload.get("next"))
    if next_url is None or request.is_json:
        return None
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        abort(400, description="next must be a relative path.")
    if not next_url.startswith("/"):
        abort(400, description="next must start with '/'.")
    return redirect(next_url)
