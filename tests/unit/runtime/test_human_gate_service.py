from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agent_platform.runtime.human_gate_service import (
    FAILED,
    SUCCEEDED,
    WAITING_HUMAN,
    HumanGateResolutionError,
    HumanGateService,
)


@dataclass
class FakeNodeRecord:
    node_id: str
    node_type: str = "human_gate"
    status: str = "PENDING"
    output_preview: str | None = None
    error_message: str | None = None
    logs: list[str] = field(default_factory=list)


@dataclass
class FakeWorkflowRecord:
    execution_id: str
    node_records: list[FakeNodeRecord] = field(default_factory=list)
    status: str = "RUNNING"


class FakeExecutionRecordsManager:
    def __init__(self) -> None:
        self.workflow_records: dict[str, FakeWorkflowRecord] = {}
        self.events: list[dict[str, str | None]] = []

    def create_workflow_record(self, execution_id: str, workflow_id: str) -> FakeWorkflowRecord:
        record = FakeWorkflowRecord(execution_id=execution_id)
        self.workflow_records[execution_id] = record
        return record

    def get_workflow_record(self, execution_id: str) -> FakeWorkflowRecord:
        return self.workflow_records[execution_id]

    def mark_node_waiting_human(self, execution_id: str, node_id: str) -> FakeNodeRecord:
        record = self._get_or_create_node_record(execution_id, node_id)
        record.status = WAITING_HUMAN
        return record

    def complete_node_record(
        self,
        execution_id: str,
        node_id: str,
        output_preview: str | None = None,
    ) -> FakeNodeRecord:
        record = self._get_or_create_node_record(execution_id, node_id)
        record.status = SUCCEEDED
        record.output_preview = output_preview
        return record

    def fail_node_record(
        self,
        execution_id: str,
        node_id: str,
        error_message: str,
    ) -> FakeNodeRecord:
        record = self._get_or_create_node_record(execution_id, node_id)
        record.status = FAILED
        record.error_message = error_message
        return record

    def append_event(
        self,
        execution_id: str,
        event_type: str,
        node_id: str | None = None,
        message: str | None = None,
        payload_ref: str | None = None,
    ) -> dict[str, str | None]:
        event = {
            "execution_id": execution_id,
            "event_type": event_type,
            "node_id": node_id,
            "message": message,
            "payload_ref": payload_ref,
        }
        self.events.append(event)
        return event

    def set_workflow_status(self, execution_id: str, status: str) -> FakeWorkflowRecord:
        workflow_record = self.get_workflow_record(execution_id)
        workflow_record.status = status
        return workflow_record

    def _get_or_create_node_record(self, execution_id: str, node_id: str) -> FakeNodeRecord:
        workflow_record = self.workflow_records[execution_id]
        for record in workflow_record.node_records:
            if record.node_id == node_id:
                return record
        record = FakeNodeRecord(node_id=node_id)
        workflow_record.node_records.append(record)
        return record


class FakeExecutionContextManager:
    def __init__(self) -> None:
        self.node_states: dict[tuple[str, str], str] = {}
        self.node_outputs: dict[tuple[str, str], dict[str, object]] = {}

    def update_node_state(self, execution_id: str, node_id: str, status: str) -> None:
        self.node_states[(execution_id, node_id)] = status

    def set_node_output(self, execution_id: str, node_id: str, output: dict[str, object]) -> None:
        self.node_outputs[(execution_id, node_id)] = output


@pytest.fixture
def setup_service() -> tuple[HumanGateService, FakeExecutionRecordsManager, FakeExecutionContextManager, str]:
    records_manager = FakeExecutionRecordsManager()
    context_manager = FakeExecutionContextManager()
    service = HumanGateService(records_manager=records_manager, context_manager=context_manager)

    execution_id = "exec-001"
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id="wf-001")
    workflow_record = records_manager.get_workflow_record(execution_id)
    workflow_record.node_records.extend(
        [
            FakeNodeRecord(node_id="outline_generation", node_type="llm_generate", status=SUCCEEDED),
            FakeNodeRecord(node_id="human_review", node_type="human_gate", status="PENDING"),
        ]
    )
    service.register_workflow_definition(
        execution_id,
        nodes=[
            {
                "id": "human_review",
                "type": "human_gate",
                "config": {"on_reject": "outline_generation"},
            }
        ],
    )
    return service, records_manager, context_manager, execution_id


def test_human_gate_service_mark_waiting_sets_waiting_and_appends_event(
    setup_service: tuple[HumanGateService, FakeExecutionRecordsManager, FakeExecutionContextManager, str],
) -> None:
    service, records_manager, context_manager, execution_id = setup_service

    service.mark_waiting(execution_id, "human_review", comment="please review")

    workflow_record = records_manager.get_workflow_record(execution_id)
    node_record = next(record for record in workflow_record.node_records if record.node_id == "human_review")
    assert node_record.status == WAITING_HUMAN
    assert context_manager.node_states[(execution_id, "human_review")] == WAITING_HUMAN
    assert records_manager.events[-1]["event_type"] == "human_gate_waiting"
    assert records_manager.events[-1]["message"] == "please review"


def test_human_gate_service_approve_sets_succeeded_and_returns_status(
    setup_service: tuple[HumanGateService, FakeExecutionRecordsManager, FakeExecutionContextManager, str],
) -> None:
    service, records_manager, context_manager, execution_id = setup_service

    result = service.approve(execution_id, "human_review", comment="approved")

    workflow_record = records_manager.get_workflow_record(execution_id)
    node_record = next(record for record in workflow_record.node_records if record.node_id == "human_review")
    assert result == SUCCEEDED
    assert node_record.status == SUCCEEDED
    assert node_record.output_preview == "approved"
    assert workflow_record.status == SUCCEEDED
    assert context_manager.node_states[(execution_id, "human_review")] == SUCCEEDED
    assert records_manager.events[-1]["event_type"] == "human_gate_approved"
    assert records_manager.events[-1]["message"] == "approved"


def test_human_gate_service_approve_node_with_decision_option_sets_context_output() -> None:
    records_manager = FakeExecutionRecordsManager()
    context_manager = FakeExecutionContextManager()
    service = HumanGateService(records_manager=records_manager, context_manager=context_manager)

    execution_id = "exec-approval"
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id="wf-approval")
    records_manager.get_workflow_record(execution_id).node_records.append(
        FakeNodeRecord(node_id="human_review", node_type="human_gate", status=WAITING_HUMAN)
    )
    service.register_workflow_definition(
        execution_id,
        nodes=[
            {
                "id": "human_review",
                "type": "human_gate",
                "config": {
                    "approval_routes": {
                        "承認": ["publish"],
                        "否認": ["revise"],
                    }
                },
            }
        ],
    )

    service.approve_node(
        execution_id=execution_id,
        node_id="human_review",
        comment="go",
        decision_option="承認",
    )

    node_record = next(
        record for record in records_manager.get_workflow_record(execution_id).node_records if record.node_id == "human_review"
    )
    assert node_record.status == SUCCEEDED
    assert node_record.output_preview == "go"
    assert context_manager.node_states[(execution_id, "human_review")] == SUCCEEDED
    assert context_manager.node_outputs[(execution_id, "human_review")]["selected_option"] == "承認"
    assert context_manager.node_outputs[(execution_id, "human_review")]["next_node"] == "publish"
    assert context_manager.node_outputs[(execution_id, "human_review")]["human_comment"] == "go"
    assert records_manager.events[-1]["event_type"] == "human_gate_approved"
    assert records_manager.events[-1]["payload_ref"] == "publish"


def test_human_gate_service_submit_sets_succeeded_and_stores_human_input(
    setup_service: tuple[HumanGateService, FakeExecutionRecordsManager, FakeExecutionContextManager, str],
) -> None:
    service, records_manager, context_manager, execution_id = setup_service

    result = service.submit(
        execution_id,
        "human_review",
        human_input={"input_file": "docs/spec.pdf", "priority": "high"},
        comment="submitted from ui",
    )

    workflow_record = records_manager.get_workflow_record(execution_id)
    node_record = next(record for record in workflow_record.node_records if record.node_id == "human_review")
    assert result == SUCCEEDED
    assert node_record.status == SUCCEEDED
    assert node_record.output_preview == "submitted from ui"
    assert workflow_record.status == SUCCEEDED
    assert context_manager.node_states[(execution_id, "human_review")] == SUCCEEDED
    assert context_manager.node_outputs[(execution_id, "human_review")]["human_input"] == {
        "input_file": "docs/spec.pdf",
        "priority": "high",
    }
    assert context_manager.node_outputs[(execution_id, "human_review")]["result"] == (
        '{"input_file": "docs/spec.pdf", "priority": "high"}'
    )
    assert records_manager.events[-1]["event_type"] == "human_gate_submitted"


def test_human_gate_service_submit_node_compatibility_method_calls_submit(
    setup_service: tuple[HumanGateService, FakeExecutionRecordsManager, FakeExecutionContextManager, str],
) -> None:
    service, records_manager, _context_manager, execution_id = setup_service

    service.submit_node(execution_id, "human_review", human_input={"text": "done"}, comment="ok")

    workflow_record = records_manager.get_workflow_record(execution_id)
    node_record = next(record for record in workflow_record.node_records if record.node_id == "human_review")
    assert node_record.status == SUCCEEDED
    assert node_record.output_preview == "ok"


def test_human_gate_service_submit_keeps_file_text_payload() -> None:
    records_manager = FakeExecutionRecordsManager()
    context_manager = FakeExecutionContextManager()
    service = HumanGateService(records_manager=records_manager, context_manager=context_manager)

    execution_id = "exec-entry-file"
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id="wf-entry")
    records_manager.get_workflow_record(execution_id).node_records.append(
        FakeNodeRecord(node_id="entry_input", node_type="human_gate", status=WAITING_HUMAN)
    )

    service.submit(
        execution_id=execution_id,
        node_id="entry_input",
        human_input={
            "text": "manual context",
            "file": {
                "filename": "input.md",
                "content_type": "text/markdown",
                "text": "# heading\nbody",
            },
        },
        comment="submitted with file",
    )

    assert context_manager.node_outputs[(execution_id, "entry_input")]["human_input"]["file"]["filename"] == "input.md"
    assert context_manager.node_outputs[(execution_id, "entry_input")]["human_input"]["file"]["text"] == "# heading\nbody"
    assert context_manager.node_outputs[(execution_id, "entry_input")]["result"] == "manual context"


def test_human_gate_service_reject_returns_explicit_fallback_when_given(
    setup_service: tuple[HumanGateService, FakeExecutionRecordsManager, FakeExecutionContextManager, str],
) -> None:
    service, records_manager, context_manager, execution_id = setup_service

    result = service.reject(
        execution_id,
        "human_review",
        fallback_node_id="task_understanding",
        comment="redo from start",
    )

    workflow_record = records_manager.get_workflow_record(execution_id)
    node_record = next(record for record in workflow_record.node_records if record.node_id == "human_review")
    assert result == "task_understanding"
    assert node_record.status == FAILED
    assert node_record.error_message == "redo from start"
    assert workflow_record.status == FAILED
    assert context_manager.node_states[(execution_id, "human_review")] == FAILED
    assert records_manager.events[-1]["event_type"] == "human_gate_rejected"
    assert records_manager.events[-1]["message"] == "redo from start"
    assert records_manager.events[-1]["payload_ref"] == "task_understanding"


def test_human_gate_service_reject_uses_on_reject_config_when_present(
    setup_service: tuple[HumanGateService, FakeExecutionRecordsManager, FakeExecutionContextManager, str],
) -> None:
    service, records_manager, _context_manager, execution_id = setup_service

    result = service.reject(execution_id, "human_review", comment="needs revision")

    assert result == "outline_generation"
    assert records_manager.get_workflow_record(execution_id).status == FAILED


def test_human_gate_service_approve_clears_waiting_human_workflow_status() -> None:
    records_manager = FakeExecutionRecordsManager()
    context_manager = FakeExecutionContextManager()
    service = HumanGateService(records_manager=records_manager, context_manager=context_manager)

    execution_id = "exec-only-human"
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id="wf-only-human")
    records_manager.get_workflow_record(execution_id).node_records.append(
        FakeNodeRecord(node_id="review", node_type="human_gate", status=WAITING_HUMAN)
    )

    service.approve(execution_id=execution_id, node_id="review", comment="done")

    assert records_manager.get_workflow_record(execution_id).status == SUCCEEDED


def test_human_gate_service_reject_uses_previous_executed_node_when_on_reject_missing() -> None:
    records_manager = FakeExecutionRecordsManager()
    context_manager = FakeExecutionContextManager()
    service = HumanGateService(records_manager=records_manager, context_manager=context_manager)

    execution_id = "exec-002"
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id="wf-002")
    workflow_record = records_manager.get_workflow_record(execution_id)
    workflow_record.node_records.extend(
        [
            FakeNodeRecord(node_id="draft_generation", node_type="llm_generate", status=SUCCEEDED),
            FakeNodeRecord(node_id="human_review", node_type="human_gate", status=WAITING_HUMAN),
        ]
    )
    service.register_workflow_definition(
        execution_id,
        nodes=[
            {
                "id": "human_review",
                "type": "human_gate",
                "config": {},
            }
        ],
    )

    result = service.reject(execution_id, "human_review", comment="go back")

    assert result == "draft_generation"


def test_human_gate_service_reject_raises_when_no_fallback_can_be_resolved() -> None:
    records_manager = FakeExecutionRecordsManager()
    context_manager = FakeExecutionContextManager()
    service = HumanGateService(records_manager=records_manager, context_manager=context_manager)

    execution_id = "exec-003"
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id="wf-003")
    workflow_record = records_manager.get_workflow_record(execution_id)
    workflow_record.node_records.append(
        FakeNodeRecord(node_id="human_review", node_type="human_gate", status=WAITING_HUMAN)
    )
    service.register_workflow_definition(
        execution_id,
        nodes=[
            {
                "id": "human_review",
                "type": "human_gate",
                "config": {},
            }
        ],
    )

    with pytest.raises(HumanGateResolutionError):
        service.reject(execution_id, "human_review", comment="cannot resolve fallback")
