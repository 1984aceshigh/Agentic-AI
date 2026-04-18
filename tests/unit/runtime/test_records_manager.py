from __future__ import annotations

import json

from agent_platform.runtime.events import (
    EVENT_TYPE_NODE_FAILED,
    EVENT_TYPE_NODE_STARTED,
    EVENT_TYPE_NODE_SUCCEEDED,
    EVENT_TYPE_NODE_WAITING_HUMAN,
    EVENT_TYPE_WORKFLOW_STATUS_CHANGED,
    NODE_STATUS_FAILED,
    NODE_STATUS_RUNNING,
    NODE_STATUS_SUCCEEDED,
    NODE_STATUS_WAITING_HUMAN,
    WORKFLOW_STATUS_FAILED,
    WORKFLOW_STATUS_RUNNING,
    WORKFLOW_STATUS_SUCCEEDED,
)
from agent_platform.runtime.records_manager import (
    ExecutionRecordNotFoundError,
    ExecutionRecordsManager,
)


def test_records_manager_create_workflow_record() -> None:
    manager = ExecutionRecordsManager()

    record = manager.create_workflow_record(
        execution_id="exec-001",
        workflow_id="workflow_a",
        workflow_version="v1",
    )

    assert record.execution_id == "exec-001"
    assert record.workflow_id == "workflow_a"
    assert record.workflow_version == "v1"
    assert record.status == WORKFLOW_STATUS_RUNNING
    assert record.started_at is not None
    assert record.finished_at is None
    assert record.node_records == []
    assert record.summary is None


def test_records_manager_get_workflow_record_raises_for_unknown_execution_id() -> None:
    manager = ExecutionRecordsManager()

    try:
        manager.get_workflow_record("missing")
        assert False, "ExecutionRecordNotFoundError was not raised"
    except ExecutionRecordNotFoundError:
        assert True


def test_records_manager_start_node_record_creates_record() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")

    record = manager.start_node_record(
        execution_id="exec-001",
        node_id="node_a",
        node_type="llm_generate",
    )

    assert record.execution_id == "exec-001"
    assert record.node_id == "node_a"
    assert record.node_type == "llm_generate"
    assert record.status == NODE_STATUS_RUNNING
    assert record.started_at is not None
    assert record.finished_at is None
    assert record.retry_count == 0
    assert record.requires_human_action is False

    workflow_record = manager.get_workflow_record("exec-001")
    assert len(workflow_record.node_records) == 1
    assert workflow_record.node_records[0] is record

    events = manager.find_events("exec-001")
    assert events[-1].event_type == EVENT_TYPE_NODE_STARTED
    assert events[-1].node_id == "node_a"


def test_records_manager_start_node_record_increments_retry_count_when_restarted() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "llm_generate")

    record = manager.start_node_record("exec-001", "node_a", "llm_generate")

    assert record.retry_count == 1
    assert record.status == NODE_STATUS_RUNNING


def test_records_manager_complete_node_record_marks_succeeded() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "llm_generate")

    record = manager.complete_node_record(
        execution_id="exec-001",
        node_id="node_a",
        output_preview="done",
    )

    assert record.status == NODE_STATUS_SUCCEEDED
    assert record.output_preview == "done"
    assert record.finished_at is not None

    events = manager.find_events("exec-001")
    assert events[-1].event_type == EVENT_TYPE_NODE_SUCCEEDED


def test_records_manager_fail_node_record_marks_failed() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "llm_generate")

    record = manager.fail_node_record(
        execution_id="exec-001",
        node_id="node_a",
        error_message="boom",
    )

    assert record.status == NODE_STATUS_FAILED
    assert record.error_message == "boom"
    assert record.finished_at is not None

    events = manager.find_events("exec-001")
    assert events[-1].event_type == EVENT_TYPE_NODE_FAILED
    assert events[-1].message == "boom"


def test_records_manager_mark_node_waiting_human_marks_waiting_human() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "human_gate")

    record = manager.mark_node_waiting_human(
        execution_id="exec-001",
        node_id="node_a",
    )

    assert record.status == NODE_STATUS_WAITING_HUMAN
    assert record.requires_human_action is True

    events = manager.find_events("exec-001")
    assert events[-1].event_type == EVENT_TYPE_NODE_WAITING_HUMAN


def test_records_manager_append_node_log_appends_log() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "llm_generate")

    record = manager.append_node_log("exec-001", "node_a", "log message")

    assert record.logs == ["log message"]


def test_records_manager_set_node_adapter_info_updates_fields() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "llm_generate")

    record = manager.set_node_adapter_info(
        execution_id="exec-001",
        node_id="node_a",
        adapter_ref="openai_responses_default",
        contract="llm_completion",
        connection_ref="OPENAI_MAIN",
        resolved_capabilities=["chat", "json_output"],
    )

    assert record.adapter_ref == "openai_responses_default"
    assert record.contract == "llm_completion"
    assert record.connection_ref == "OPENAI_MAIN"
    assert record.resolved_capabilities == ["chat", "json_output"]


def test_records_manager_append_event_adds_event() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")

    event = manager.append_event(
        execution_id="exec-001",
        event_type="custom_event",
        node_id="node_a",
        message="hello",
        payload_ref="artifact://payload/1",
    )

    assert event.execution_id == "exec-001"
    assert event.event_type == "custom_event"
    assert event.node_id == "node_a"
    assert event.message == "hello"
    assert event.payload_ref == "artifact://payload/1"

    events = manager.find_events("exec-001")
    assert events[-1] == event


def test_records_manager_set_workflow_status_updates_status() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")

    succeeded = manager.set_workflow_status("exec-001", WORKFLOW_STATUS_SUCCEEDED)
    assert succeeded.status == WORKFLOW_STATUS_SUCCEEDED
    assert succeeded.finished_at is not None

    failed = manager.set_workflow_status("exec-001", WORKFLOW_STATUS_FAILED)
    assert failed.status == WORKFLOW_STATUS_FAILED
    assert failed.finished_at is not None

    events = manager.find_events("exec-001")
    assert events[-1].event_type == EVENT_TYPE_WORKFLOW_STATUS_CHANGED


def test_records_manager_find_node_records_returns_node_records() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    node_a = manager.start_node_record("exec-001", "node_a", "llm_generate")
    node_b = manager.start_node_record("exec-001", "node_b", "llm_review")

    records = manager.find_node_records("exec-001")

    assert records == [node_a, node_b]


def test_records_manager_persists_and_restores_state(tmp_path) -> None:
    storage_path = tmp_path / "runtime" / "execution_records.json"
    manager = ExecutionRecordsManager(storage_path=storage_path)
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "llm")
    manager.complete_node_record("exec-001", "node_a", output_preview="ok")
    manager.set_workflow_status("exec-001", WORKFLOW_STATUS_SUCCEEDED)

    assert storage_path.exists() is True
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert persisted["workflow_records"][0]["execution_id"] == "exec-001"

    restored = ExecutionRecordsManager(storage_path=storage_path)
    workflow_record = restored.get_workflow_record("exec-001")
    assert workflow_record.workflow_id == "workflow_a"
    assert workflow_record.status == WORKFLOW_STATUS_SUCCEEDED
    assert len(workflow_record.node_records) == 1
    assert workflow_record.node_records[0].output_preview == "ok"


def test_records_manager_list_workflow_records_returns_newest_first() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-old", "workflow_a")
    manager.create_workflow_record("exec-new", "workflow_b")

    records = manager.list_workflow_records()

    assert [record.execution_id for record in records] == ["exec-new", "exec-old"]

    filtered = manager.list_workflow_records("workflow_a")
    assert [record.execution_id for record in filtered] == ["exec-old"]


def test_records_manager_delete_workflow_record_removes_related_data() -> None:
    manager = ExecutionRecordsManager()
    manager.create_workflow_record("exec-001", "workflow_a")
    manager.start_node_record("exec-001", "node_a", "llm_generate")
    manager.append_event("exec-001", "custom_event", node_id="node_a", message="hello")

    deleted = manager.delete_workflow_record("exec-001")

    assert deleted.execution_id == "exec-001"
    assert deleted.workflow_id == "workflow_a"
    assert manager.list_workflow_records() == []

    try:
        manager.get_workflow_record("exec-001")
        assert False, "ExecutionRecordNotFoundError was not raised"
    except ExecutionRecordNotFoundError:
        assert True


def test_records_manager_delete_workflow_record_raises_for_unknown_execution_id() -> None:
    manager = ExecutionRecordsManager()

    try:
        manager.delete_workflow_record("missing")
        assert False, "ExecutionRecordNotFoundError was not raised"
    except ExecutionRecordNotFoundError:
        assert True
