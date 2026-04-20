from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

from flask import Blueprint, abort, jsonify, redirect, request

from .dependencies import (
    get_dependency_container,
    get_latest_execution_ids,
    get_execution_service,
    get_human_gate_service,
    get_read_model_service,
    get_rerun_service,
    get_workflow_graphs,
)

action_bp = Blueprint("action_routes", __name__, url_prefix="/actions")


def _parse_human_input(payload: dict[str, Any]) -> dict[str, Any]:
    raw_input = payload.get("human_input")
    if isinstance(raw_input, dict):
        return {str(key): value for key, value in raw_input.items()}

    if request.is_json:
        return {}

    # form post fallback
    parsed: dict[str, Any] = {}
    raw_json = _optional_str(payload.get("human_input_json"))
    if raw_json:
        try:
            loaded = json.loads(raw_json)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            parsed.update({str(key): value for key, value in loaded.items()})

    raw_text = _optional_str(payload.get("human_input_text"))
    if raw_text:
        parsed["text"] = raw_text

    upload = request.files.get("human_input_file")
    if upload is not None and str(upload.filename or "").strip():
        try:
            extracted_text = _extract_text_from_uploaded_file(
                filename=str(upload.filename),
                file_bytes=upload.read(),
            )
        except ValueError as exc:
            abort(400, description=str(exc))
        parsed["file"] = {
            "filename": str(upload.filename),
            "content_type": _optional_str(upload.content_type),
            "text": extracted_text,
        }
    return parsed


@action_bp.post("/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/approve")
def approve_node(workflow_id: str, execution_id: str, node_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    comment = _optional_str(payload.get("comment"))
    decision_option = _optional_str(payload.get("decision_option"))

    _register_human_gate_definition_if_supported(workflow_id=workflow_id, execution_id=execution_id)

    human_gate_service = get_human_gate_service()
    try:
        if hasattr(human_gate_service, "approve_node"):
            human_gate_service.approve_node(
                execution_id=execution_id,
                node_id=node_id,
                comment=comment,
                decision_option=decision_option,
            )
        else:
            human_gate_service.approve(execution_id=execution_id, node_id=node_id, comment=comment)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    _resume_workflow_after_human_action(workflow_id=workflow_id, execution_id=execution_id)

    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response

    return jsonify(
        {
            "status": "ok",
            "action": "approve",
            "node_id": node_id,
            "selected_option": decision_option,
        }
    )


@action_bp.post("/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/reject")
def reject_node(workflow_id: str, execution_id: str, node_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    fallback_node_id = _optional_str(payload.get("fallback_node_id"))
    comment = _optional_str(payload.get("comment"))

    _register_human_gate_definition_if_supported(workflow_id=workflow_id, execution_id=execution_id)

    human_gate_service = get_human_gate_service()
    try:
        if hasattr(human_gate_service, "reject_node"):
            human_gate_service.reject_node(
                execution_id=execution_id,
                node_id=node_id,
                fallback_node_id=fallback_node_id,
                comment=comment,
            )
        else:
            human_gate_service.reject(
                execution_id=execution_id,
                node_id=node_id,
                fallback_node_id=fallback_node_id,
                comment=comment,
            )
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    _resume_workflow_after_human_action(workflow_id=workflow_id, execution_id=execution_id)

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


@action_bp.post("/workflows/<workflow_id>/executions/<execution_id>/nodes/<node_id>/submit")
def submit_node(workflow_id: str, execution_id: str, node_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    comment = _optional_str(payload.get("comment"))
    human_input = _parse_human_input(payload)

    _register_human_gate_definition_if_supported(workflow_id=workflow_id, execution_id=execution_id)

    human_gate_service = get_human_gate_service()
    try:
        if hasattr(human_gate_service, "submit_node"):
            human_gate_service.submit_node(
                execution_id=execution_id,
                node_id=node_id,
                human_input=human_input,
                comment=comment,
            )
        elif hasattr(human_gate_service, "submit"):
            human_gate_service.submit(
                execution_id=execution_id,
                node_id=node_id,
                human_input=human_input,
                comment=comment,
            )
        else:
            raise RuntimeError("HumanGateService does not support submit action.")
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    _resume_workflow_after_human_action(workflow_id=workflow_id, execution_id=execution_id)

    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response

    return jsonify(
        {
            "status": "ok",
            "action": "submit",
            "node_id": node_id,
            "human_input": human_input,
        }
    )


@action_bp.post("/workflows/<workflow_id>/executions/<execution_id>/rerun")
def rerun_workflow(workflow_id: str, execution_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    from_node_id = _optional_str(payload.get("from_node_id"))
    if not from_node_id:
        abort(400, description="from_node_id is required.")

    try:
        rerun_service = get_rerun_service()
        if hasattr(rerun_service, "rerun_from_node"):
            rerun_service.rerun_from_node(execution_id=execution_id, from_node_id=from_node_id)
        else:
            execution_service = get_execution_service()
            execution_service.rerun_from_node(
                workflow_id=workflow_id,
                execution_id=execution_id,
                from_node_id=from_node_id,
            )
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


@action_bp.post("/workflows/<workflow_id>/run")
def run_workflow(workflow_id: str):
    _ensure_workflow_exists(workflow_id)
    payload = _get_payload()
    global_inputs = payload.get("global_inputs")
    if not isinstance(global_inputs, dict):
        global_inputs = None

    execution_service = get_execution_service()
    execution_id = execution_service.run_workflow(workflow_id, global_inputs=global_inputs)

    next_url = _optional_str(payload.get("next"))
    if next_url is not None and "{execution_id}" in next_url:
        payload = dict(payload)
        payload["next"] = next_url.replace("{execution_id}", execution_id)

    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response

    if not request.is_json:
        return redirect(f"/workflows/{workflow_id}/executions/{execution_id}/nodes")

    return jsonify(
        {
            "status": "ok",
            "action": "run",
            "workflow_id": workflow_id,
            "execution_id": execution_id,
        }
    )


@action_bp.post("/executions/<execution_id>/delete")
def delete_execution(execution_id: str):
    payload = _get_payload()
    read_model_service = get_read_model_service()
    records_manager = getattr(read_model_service, "_records_manager", None)
    if records_manager is None or not hasattr(records_manager, "delete_workflow_record"):
        abort(500, description="Execution record delete is not supported.")

    try:
        deleted_record = records_manager.delete_workflow_record(execution_id)
    except KeyError as exc:
        raise abort(404, description=str(exc)) from exc

    workflow_id = str(getattr(deleted_record, "workflow_id", ""))
    if workflow_id:
        latest_execution_ids = get_latest_execution_ids()
        if latest_execution_ids.get(workflow_id) == execution_id:
            remaining = records_manager.list_workflow_records(workflow_id)
            latest_execution_ids[workflow_id] = remaining[0].execution_id if remaining else None

    redirect_response = _maybe_redirect(payload)
    if redirect_response is not None:
        return redirect_response

    if not request.is_json:
        return redirect("/executions")

    return jsonify(
        {
            "status": "ok",
            "action": "delete_execution",
            "execution_id": execution_id,
            "workflow_id": workflow_id or None,
        }
    )


def _ensure_workflow_exists(workflow_id: str) -> None:
    if workflow_id not in get_workflow_graphs():
        abort(404, description=f"Unknown workflow_id: {workflow_id}")


def _register_human_gate_definition_if_supported(*, workflow_id: str, execution_id: str) -> None:
    graph = get_workflow_graphs().get(workflow_id)
    if graph is None:
        return
    service = get_human_gate_service()
    register_definition = getattr(service, "register_workflow_definition", None)
    if not callable(register_definition):
        return

    nodes: list[dict[str, Any]] = []
    for node in graph.nodes.values():
        node_id = str(getattr(node, "id", "") or "").strip()
        if not node_id:
            continue
        config = getattr(node, "config", None)
        node_config = dict(config) if isinstance(config, dict) else {}
        nodes.append({"id": node_id, "config": node_config})
    register_definition(execution_id, nodes)


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


def _extract_text_from_uploaded_file(*, filename: str, file_bytes: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log"}:
        return file_bytes.decode("utf-8", errors="ignore")
    if ext == ".docx":
        return _extract_docx_text(file_bytes)
    if ext == ".pdf":
        return _extract_pdf_text(file_bytes)
    raise ValueError(f"Unsupported file type: {ext or '(none)'}")


def _extract_docx_text(file_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        with archive.open("word/document.xml") as stream:
            xml_text = stream.read().decode("utf-8", errors="ignore")

    root = ElementTree.fromstring(xml_text)
    paragraphs: list[str] = []
    for paragraph in root.iterfind(".//{*}p"):
        texts = [node.text for node in paragraph.iterfind(".//{*}t") if node.text]
        if texts:
            paragraphs.append("".join(texts).strip())
    return "\n".join(item for item in paragraphs if item)


def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception as exc:  # pragma: no cover - optional lib/runtime format
        raise ValueError("PDF extraction requires pypdf package") from exc


def _resume_workflow_after_human_action(*, workflow_id: str, execution_id: str) -> None:
    """Resume halted workflow if ExecutionService supports resume_workflow()."""
    container = get_dependency_container()
    execution_service = container.get("execution_service")
    if execution_service is None:
        return
    resume = getattr(execution_service, "resume_workflow", None)
    if callable(resume):
        resume(workflow_id=workflow_id, execution_id=execution_id)
