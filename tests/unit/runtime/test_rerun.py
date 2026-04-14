from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_platform.runtime.rerun import (
    EVENT_TYPE_RERUN_PREPARED,
    RerunService,
    WORKFLOW_STATUS_RERUNNING,
)


@dataclass
class DummyEvent:
    execution_id: str
    event_type: str
    node_id: str | None = None
    message: str | None = None
    payload_ref: str | None = None


@dataclass
class DummyContext:
    execution_id: str
    workflow_id: str
    workflow_version: str | None = None
    global_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_states: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    events: list[DummyEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DummyNodeRecord:
    execution_id: str
    node_id: str
    node_type: str
    status: str
    started_at: str | None = "started"
    finished_at: str | None = "finished"
    input_preview: str | None = None
    output_preview: str | None = "old output"
    full_input_ref: str | None = None
    full_output_ref: str | None = "artifact://old"
    error_message: str | None = "old error"
    logs: list[str] = field(default_factory=lambda: ["old log"])
    retry_count: int = 0
    requires_human_action: bool = True


@dataclass
class DummyWorkflowRecord:
    execution_id: str
    workflow_id: str
    workflow_version: str | None = None
    status: str = "FAILED"
    started_at: str | None = "started"
    finished_at: str | None = "finished"
    node_records: list[DummyNodeRecord] = field(default_factory=list)
    summary: str | None = None


@dataclass
class DummyNode:
    id: str


@dataclass
class DummyEdge:
    source: str
    target: str


@dataclass
class DummyGraph:
    nodes: list[DummyNode]
    edges: list[DummyEdge]


class FakeContextManager:
    def __init__(self, context: DummyContext) -> None:
        self._context = context

    def get_context(self, execution_id: str) -> DummyContext:
        assert execution_id == self._context.execution_id
        return self._context

    def save_context(self, context: DummyContext) -> None:
        self._context = context

    def append_event(self, execution_id: str, event: DummyEvent) -> DummyContext:
        context = self.get_context(execution_id)
        context.events.append(event)
        return context


class FakeRecordsManager:
    def __init__(self, workflow_record: DummyWorkflowRecord) -> None:
        self._workflow_record = workflow_record
        self._events: list[DummyEvent] = []

    def get_workflow_record(self, execution_id: str) -> DummyWorkflowRecord:
        assert execution_id == self._workflow_record.execution_id
        return self._workflow_record

    def get_node_record(self, execution_id: str, node_id: str) -> DummyNodeRecord:
        assert execution_id == self._workflow_record.execution_id
        for record in self._workflow_record.node_records:
            if record.node_id == node_id:
                return record
        raise KeyError(node_id)

    def set_workflow_status(self, execution_id: str, status: str) -> DummyWorkflowRecord:
        workflow_record = self.get_workflow_record(execution_id)
        workflow_record.status = status
        return workflow_record

    def append_event(
        self,
        execution_id: str,
        event_type: str,
        node_id: str | None = None,
        message: str | None = None,
        payload_ref: str | None = None,
    ) -> DummyEvent:
        assert execution_id == self._workflow_record.execution_id
        event = DummyEvent(
            execution_id=execution_id,
            event_type=event_type,
            node_id=node_id,
            message=message,
            payload_ref=payload_ref,
        )
        self._events.append(event)
        return event

    def find_events(self, execution_id: str) -> list[DummyEvent]:
        assert execution_id == self._workflow_record.execution_id
        return list(self._events)


def _build_graph() -> DummyGraph:
    return DummyGraph(
        nodes=[
            DummyNode(id="n1"),
            DummyNode(id="n2"),
            DummyNode(id="n3"),
            DummyNode(id="n4"),
        ],
        edges=[
            DummyEdge(source="n1", target="n2"),
            DummyEdge(source="n2", target="n3"),
            DummyEdge(source="n2", target="n4"),
        ],
    )


def _build_context() -> DummyContext:
    return DummyContext(
        execution_id="exec-1",
        workflow_id="wf-1",
        workflow_version="v1",
        node_outputs={
            "n1": {"result": "keep"},
            "n2": {"result": "drop-2"},
            "n3": {"result": "drop-3"},
            "n4": {"result": "drop-4"},
        },
        node_states={
            "n1": "SUCCEEDED",
            "n2": "FAILED",
            "n3": "SUCCEEDED",
            "n4": "WAITING_HUMAN",
        },
    )


def _build_workflow_record() -> DummyWorkflowRecord:
    return DummyWorkflowRecord(
        execution_id="exec-1",
        workflow_id="wf-1",
        workflow_version="v1",
        status="FAILED",
        node_records=[
            DummyNodeRecord(
                execution_id="exec-1",
                node_id="n1",
                node_type="llm_generate",
                status="SUCCEEDED",
                logs=["keep"],
                error_message=None,
                requires_human_action=False,
            ),
            DummyNodeRecord(
                execution_id="exec-1",
                node_id="n2",
                node_type="llm_review",
                status="FAILED",
            ),
            DummyNodeRecord(
                execution_id="exec-1",
                node_id="n3",
                node_type="deterministic_transform",
                status="SUCCEEDED",
            ),
            DummyNodeRecord(
                execution_id="exec-1",
                node_id="n4",
                node_type="human_gate",
                status="WAITING_HUMAN",
            ),
        ],
    )


def test_collect_downstream_nodes_includes_from_node_and_downstream_nodes() -> None:
    service = RerunService(context_manager=None, records_manager=None)

    downstream = service.collect_downstream_nodes(_build_graph(), "n2")

    assert downstream == ["n2", "n3", "n4"]


def test_collect_downstream_nodes_raises_when_start_node_is_missing() -> None:
    service = RerunService(context_manager=None, records_manager=None)

    try:
        service.collect_downstream_nodes(_build_graph(), "missing")
    except ValueError as exc:
        assert "missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ValueError was not raised")


def test_prepare_rerun_resets_downstream_context_state_and_outputs() -> None:
    context = _build_context()
    workflow_record = _build_workflow_record()
    context_manager = FakeContextManager(context)
    records_manager = FakeRecordsManager(workflow_record)
    service = RerunService(context_manager=context_manager, records_manager=records_manager)

    updated_context = service.prepare_rerun("exec-1", _build_graph(), "n2")

    assert updated_context.node_states["n1"] == "SUCCEEDED"
    assert updated_context.node_states["n2"] == "PENDING"
    assert updated_context.node_states["n3"] == "PENDING"
    assert updated_context.node_states["n4"] == "PENDING"

    assert updated_context.node_outputs["n1"] == {"result": "keep"}
    assert "n2" not in updated_context.node_outputs
    assert "n3" not in updated_context.node_outputs
    assert "n4" not in updated_context.node_outputs


def test_prepare_rerun_resets_downstream_node_records_and_updates_workflow_status() -> None:
    context_manager = FakeContextManager(_build_context())
    workflow_record = _build_workflow_record()
    records_manager = FakeRecordsManager(workflow_record)
    service = RerunService(context_manager=context_manager, records_manager=records_manager)

    service.prepare_rerun("exec-1", _build_graph(), "n2")

    n1 = records_manager.get_node_record("exec-1", "n1")
    n2 = records_manager.get_node_record("exec-1", "n2")
    n3 = records_manager.get_node_record("exec-1", "n3")
    n4 = records_manager.get_node_record("exec-1", "n4")

    assert n1.status == "SUCCEEDED"
    assert n1.logs == ["keep"]

    for record in (n2, n3, n4):
        assert record.status == "PENDING"
        assert record.started_at is None
        assert record.finished_at is None
        assert record.output_preview is None
        assert record.full_output_ref is None
        assert record.error_message is None
        assert record.logs == []
        assert record.requires_human_action is False

    assert workflow_record.status == WORKFLOW_STATUS_RERUNNING


def test_prepare_rerun_appends_rerun_event_and_mirrors_it_to_context() -> None:
    context = _build_context()
    context_manager = FakeContextManager(context)
    records_manager = FakeRecordsManager(_build_workflow_record())
    service = RerunService(context_manager=context_manager, records_manager=records_manager)

    service.prepare_rerun("exec-1", _build_graph(), "n2")

    events = records_manager.find_events("exec-1")
    assert len(events) == 1
    assert events[0].event_type == EVENT_TYPE_RERUN_PREPARED
    assert events[0].node_id == "n2"
    assert events[0].payload_ref == "n2"
    assert "Affected nodes: n2, n3, n4" in (events[0].message or "")

    assert len(context.events) == 1
    assert context.events[0].event_type == EVENT_TYPE_RERUN_PREPARED
