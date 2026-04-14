from __future__ import annotations

from agent_platform.models import ExecutionContext, NodeExecutionRecord, NodeStatus, WorkflowExecutionRecord


def test_execution_context_default_factories_work() -> None:
    context = ExecutionContext(execution_id="exec-1", workflow_id="workflow-1")
    assert context.global_inputs == {}
    assert context.node_outputs == {}
    assert context.node_states == {}
    assert context.artifacts == {}
    assert context.events == []
    assert context.metadata == {}


def test_node_execution_record_accepts_node_status() -> None:
    record = NodeExecutionRecord(
        execution_id="exec-1",
        node_id="node-1",
        node_type="llm_generate",
        status=NodeStatus.PENDING,
    )
    assert record.status is NodeStatus.PENDING


def test_workflow_execution_record_can_be_created() -> None:
    record = WorkflowExecutionRecord(
        execution_id="exec-1",
        workflow_id="workflow-1",
        status=NodeStatus.RUNNING,
    )
    assert record.execution_id == "exec-1"
    assert record.node_records == []
