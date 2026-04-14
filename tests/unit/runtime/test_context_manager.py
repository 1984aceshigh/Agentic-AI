from __future__ import annotations

import uuid
from typing import cast

import pytest

from agent_platform.models.execution import ExecutionEvent
from agent_platform.runtime.context_manager import (
    ExecutionContextManager,
    ExecutionContextNotFoundError,
)


def test_context_manager_create_context_assigns_uuid4_and_initial_values() -> None:
    manager = ExecutionContextManager()

    context = manager.create_context(
        workflow_id="sample_workflow",
        workflow_version="v1",
        global_inputs={"request": "hello"},
    )

    parsed_uuid = uuid.UUID(context.execution_id)
    assert parsed_uuid.version == 4
    assert context.workflow_id == "sample_workflow"
    assert context.workflow_version == "v1"
    assert context.global_inputs == {"request": "hello"}
    assert context.node_outputs == {}
    assert context.node_states == {}
    assert context.artifacts == {}
    assert context.events == []
    assert context.metadata == {"logs": []}


def test_context_manager_get_context_returns_saved_context() -> None:
    manager = ExecutionContextManager()
    created = manager.create_context(workflow_id="sample_workflow")

    loaded = manager.get_context(created.execution_id)

    assert loaded is created


def test_context_manager_get_context_raises_for_unknown_execution_id() -> None:
    manager = ExecutionContextManager()

    with pytest.raises(ExecutionContextNotFoundError):
        manager.get_context("missing-execution-id")


def test_context_manager_save_context_overwrites_existing_context() -> None:
    manager = ExecutionContextManager()
    context = manager.create_context(workflow_id="sample_workflow")

    context.metadata["note"] = "updated"
    manager.save_context(context)

    loaded = manager.get_context(context.execution_id)
    assert loaded.metadata["note"] == "updated"


def test_context_manager_update_node_state_updates_node_states() -> None:
    manager = ExecutionContextManager()
    context = manager.create_context(workflow_id="sample_workflow")

    updated = manager.update_node_state(
        execution_id=context.execution_id,
        node_id="node_a",
        status="RUNNING",
    )

    assert updated.node_states["node_a"] == "RUNNING"
    assert manager.get_context(context.execution_id).node_states["node_a"] == "RUNNING"


def test_context_manager_set_node_output_updates_and_merges_outputs() -> None:
    manager = ExecutionContextManager()
    context = manager.create_context(workflow_id="sample_workflow")

    manager.set_node_output(
        execution_id=context.execution_id,
        node_id="node_a",
        output={"answer": "first"},
    )
    updated = manager.set_node_output(
        execution_id=context.execution_id,
        node_id="node_a",
        output={"score": 95},
    )

    assert updated.node_outputs["node_a"] == {
        "answer": "first",
        "score": 95,
    }


def test_context_manager_append_log_appends_message_to_metadata_logs() -> None:
    manager = ExecutionContextManager()
    context = manager.create_context(workflow_id="sample_workflow")

    manager.append_log(context.execution_id, "started")
    updated = manager.append_log(context.execution_id, "finished")

    assert updated.metadata["logs"] == ["started", "finished"]


def test_context_manager_append_event_appends_event() -> None:
    manager = ExecutionContextManager()
    context = manager.create_context(workflow_id="sample_workflow")

    event = cast(ExecutionEvent, {"event_type": "node_started", "node_id": "node_a"})

    updated = manager.append_event(context.execution_id, event)

    assert len(updated.events) == 1
    assert updated.events[0] == event


def test_context_manager_set_artifact_updates_artifacts() -> None:
    manager = ExecutionContextManager()
    context = manager.create_context(workflow_id="sample_workflow")

    updated = manager.set_artifact(
        execution_id=context.execution_id,
        key="draft_markdown",
        value="# Title",
    )

    assert updated.artifacts["draft_markdown"] == "# Title"
