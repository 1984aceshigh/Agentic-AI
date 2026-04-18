from __future__ import annotations

from datetime import datetime, timezone

from agent_platform.models import ExecutionEvent, GraphEdge, GraphModel, GraphNode
from agent_platform.runtime.context_manager import ExecutionContextManager
from agent_platform.runtime.records_manager import ExecutionRecordsManager
from agent_platform.ui_api import ReadModelService


UTC = timezone.utc


def make_graph_model() -> GraphModel:
    return GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step3"],
        direction="TD",
        nodes={
            "step1": GraphNode(id="step1", type="llm_generate", name="Draft", group="analysis"),
            "step2": GraphNode(
                id="step2",
                type="llm",
                name="Memory Lookup",
                group="analysis",
                config={"task": "read"},
            ),
            "step3": GraphNode(id="step3", type="rag_retrieve", name="Knowledge Lookup", group="review"),
        },
        edges=[
            GraphEdge(from_node="step1", to_node="step2"),
            GraphEdge(from_node="step2", to_node="step3"),
        ],
    )


def build_service() -> tuple[ReadModelService, ExecutionContextManager, ExecutionRecordsManager]:
    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager()
    service = ReadModelService(context_manager=context_manager, records_manager=records_manager)
    return service, context_manager, records_manager


def prepare_execution() -> tuple[ReadModelService, GraphModel, str]:
    service, context_manager, records_manager = build_service()
    graph = make_graph_model()

    context = context_manager.create_context(workflow_id=graph.workflow_id)
    execution_id = context.execution_id
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id=graph.workflow_id)

    record1 = records_manager.start_node_record(execution_id, "step1", "llm_generate")
    record1.input_preview = "task input"
    record1.started_at = datetime(2026, 4, 12, 1, 0, tzinfo=UTC)
    records_manager.complete_node_record(execution_id, "step1", output_preview="drafted")
    record1.finished_at = datetime(2026, 4, 12, 1, 1, tzinfo=UTC)
    records_manager.append_node_log(execution_id, "step1", "draft complete")

    record2 = records_manager.start_node_record(execution_id, "step2", "llm")
    record2.input_preview = "lookup prior notes"
    record2.started_at = datetime(2026, 4, 12, 1, 2, tzinfo=UTC)
    records_manager.mark_node_waiting_human(execution_id, "step2")
    records_manager.set_node_adapter_info(
        execution_id,
        "step2",
        adapter_ref="sqlite_memory_default",
        contract="memory_store",
        connection_ref="LOCAL_SQLITE_MEMORY",
        resolved_capabilities=["read", "write"],
    )
    records_manager.append_node_log(execution_id, "step2", "memory lookup pending review")

    record3 = records_manager.start_node_record(execution_id, "step3", "rag_retrieve")
    record3.input_preview = "retrieve similar docs"
    record3.started_at = datetime(2026, 4, 12, 1, 3, tzinfo=UTC)
    records_manager.fail_node_record(execution_id, "step3", error_message="retrieval failed")
    record3.finished_at = datetime(2026, 4, 12, 1, 4, tzinfo=UTC)
    records_manager.append_node_log(execution_id, "step3", "retrieval failed once")
    records_manager.set_workflow_status(execution_id, "FAILED")

    context_manager.update_node_state(execution_id, "step1", "SUCCEEDED")
    context_manager.update_node_state(execution_id, "step2", "WAITING_HUMAN")
    context_manager.update_node_state(execution_id, "step3", "FAILED")
    context_manager.set_node_output(
        execution_id,
        "step2",
        {
            "records": [
                {"record_id": "mem-1", "scope": "workflow", "text": "previous memo"},
            ],
            "count": 1,
        },
    )
    context_manager.set_node_output(
        execution_id,
        "step3",
        {
            "hits": [
                {"chunk_id": "doc-1", "score": 0.91, "text": "relevant chunk", "metadata": {"source": "kb/risk.md"}},
            ],
            "count": 1,
            "query_text": "risk management",
        },
    )
    context_manager.set_artifact(execution_id, "final_report", {"path": "artifacts/final.md"})
    context_manager.append_event(
        execution_id,
        ExecutionEvent(
            event_type="node_waiting_human",
            timestamp=datetime(2026, 4, 12, 1, 2, 30, tzinfo=UTC),
            execution_id=execution_id,
            node_id="step2",
            message="approval required",
        ),
    )
    context_manager.append_event(
        execution_id,
        ExecutionEvent(
            event_type="node_failed",
            timestamp=datetime(2026, 4, 12, 1, 4, 0, tzinfo=UTC),
            execution_id=execution_id,
            node_id="step3",
            message="retrieval failed",
            payload_ref="artifacts/errors/step3.json",
        ),
    )

    return service, graph, execution_id



def test_build_workflow_summary_counts_waiting_and_failed_nodes() -> None:
    service, graph, execution_id = prepare_execution()

    summary = service.build_workflow_summary(graph, execution_id)

    assert summary.workflow_id == "sample_workflow"
    assert summary.workflow_name == "Sample Workflow"
    assert summary.last_execution_id == execution_id
    assert summary.last_status == "FAILED"
    assert summary.last_updated_at == "2026-04-12 01:04:00"
    assert summary.waiting_human_count == 1
    assert summary.failed_count == 1


def test_build_execution_summaries_returns_records() -> None:
    service, _, execution_id = prepare_execution()

    summaries = service.build_execution_summaries()

    assert len(summaries) == 1
    assert summaries[0].execution_id == execution_id
    assert summaries[0].workflow_id == "sample_workflow"
    assert summaries[0].status == "FAILED"
    assert summaries[0].node_count == 3
    assert summaries[0].waiting_human_count == 1
    assert summaries[0].failed_count == 1


def test_build_execution_detail_returns_node_results() -> None:
    service, _, execution_id = prepare_execution()

    detail = service.build_execution_detail(execution_id)

    assert detail.execution_id == execution_id
    assert detail.workflow_id == "sample_workflow"
    assert detail.status == "FAILED"
    assert detail.node_count == 3
    assert detail.waiting_human_count == 1
    assert detail.failed_count == 1
    assert detail.event_count == 7
    assert [item.node_id for item in detail.node_results] == ["step1", "step2", "step3"]



def test_build_node_cards_returns_flat_ui_friendly_models() -> None:
    service, graph, execution_id = prepare_execution()

    cards = service.build_node_cards(graph, execution_id)

    assert [card.node_id for card in cards] == ["step1", "step2", "step3"]
    assert cards[0].node_name == "Draft"
    assert cards[0].group == "analysis"
    assert cards[0].node_type == "llm"
    assert cards[0].task == "generate"
    assert cards[0].status == "SUCCEEDED"
    assert cards[0].retryable is True
    assert cards[0].started_at == "2026-04-12 01:00:00"
    assert cards[0].finished_at == "2026-04-12 01:01:00"
    assert cards[0].output_preview == "drafted"
    assert cards[1].status == "WAITING_HUMAN"
    assert cards[1].task == "read"
    assert cards[1].requires_human_action is True
    assert cards[1].started_at == "2026-04-12 01:02:00"
    assert cards[1].finished_at is None
    assert cards[1].output_preview is None
    assert cards[2].status == "FAILED"
    assert cards[2].task == "retrieve"
    assert cards[2].retryable is True
    assert cards[2].error_message == "retrieval failed"


def test_build_node_cards_without_execution_returns_pending_nodes() -> None:
    service, _, _ = build_service()
    graph = make_graph_model()

    cards = service.build_node_cards(graph, execution_id=None)

    assert [card.node_id for card in cards] == ["step1", "step2", "step3"]
    assert all(card.status == "PENDING" for card in cards)
    assert all(card.started_at is None for card in cards)
    assert all(card.finished_at is None for card in cards)



def test_build_node_detail_extracts_memory_records_and_event_history() -> None:
    service, graph, execution_id = prepare_execution()

    detail = service.build_node_detail(graph, execution_id, "step2")

    assert detail.node_id == "step2"
    assert detail.node_name == "Memory Lookup"
    assert detail.node_type == "llm"
    assert detail.task == "read"
    assert detail.status == "WAITING_HUMAN"
    assert detail.input_preview == "lookup prior notes"
    assert detail.logs == ["memory lookup pending review"]
    assert detail.adapter_ref == "sqlite_memory_default"
    assert detail.contract == "memory_store"
    assert detail.connection_ref == "LOCAL_SQLITE_MEMORY"
    assert detail.resolved_capabilities == ["read", "write"]
    assert detail.memory_records == [
        {"record_id": "mem-1", "scope": "workflow", "text": "previous memo"}
    ]
    assert detail.memory_count == 1
    assert detail.rag_hits == []
    assert detail.event_history == [
        {
            "event_type": "node_waiting_human",
            "timestamp": "2026-04-12 01:02:30",
            "execution_id": execution_id,
            "node_id": "step2",
            "message": "approval required",
            "payload_ref": None,
        }
    ]



def test_build_node_detail_extracts_rag_hits() -> None:
    service, graph, execution_id = prepare_execution()

    detail = service.build_node_detail(graph, execution_id, "step3")

    assert detail.node_id == "step3"
    assert detail.node_type == "llm"
    assert detail.task == "retrieve"
    assert detail.status == "FAILED"
    assert detail.error_message == "retrieval failed"
    assert detail.memory_records == []
    assert detail.rag_query_text == "risk management"
    assert detail.rag_hits == [
        {
            "chunk_id": "doc-1",
            "score": 0.91,
            "text": "relevant chunk",
            "metadata": {"source": "kb/risk.md"},
        }
    ]
    assert detail.rag_count == 1
    assert detail.event_history[0]["event_type"] == "node_failed"


def test_build_node_detail_extracts_nested_llm_memory_and_rag_outputs() -> None:
    service, context_manager, records_manager = build_service()
    graph = GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step1"],
        direction="TD",
        nodes={
            "step1": GraphNode(
                id="step1",
                type="llm",
                name="Assistant",
                group="analysis",
                config={"task": "generate"},
            ),
        },
        edges=[],
    )

    context = context_manager.create_context(workflow_id=graph.workflow_id)
    execution_id = context.execution_id
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id=graph.workflow_id)
    records_manager.start_node_record(execution_id, "step1", "llm")
    records_manager.complete_node_record(execution_id, "step1", output_preview="ok")
    context_manager.update_node_state(execution_id, "step1", "SUCCEEDED")
    context_manager.set_node_output(
        execution_id,
        "step1",
        {
            "task": "generate",
            "result": "ok",
            "memory": {
                "records": [
                    {"record_id": "mem-1", "scope": "workflow", "text": "prior note"},
                    {"record_id": "mem-2", "scope": "workflow", "text": "another note"},
                ],
                "count": 2,
            },
            "rag": {
                "query_text": "current question",
                "hits": [
                    {
                        "chunk_id": "doc-1",
                        "score": 0.95,
                        "text": "knowledge",
                        "metadata": {"source": "kb/source.md"},
                    }
                ],
                "count": 1,
            },
        },
    )

    detail = service.build_node_detail(graph, execution_id, "step1")

    assert detail.memory_count == 2
    assert len(detail.memory_records) == 2
    assert detail.rag_query_text == "current question"
    assert detail.rag_count == 1
    assert detail.rag_hits[0]["chunk_id"] == "doc-1"


def test_build_node_cards_legacy_llm_review_maps_to_assessment_task() -> None:
    service, context_manager, records_manager = build_service()
    graph = GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="review",
        end_nodes=["review"],
        direction="TD",
        nodes={
            "review": GraphNode(id="review", type="llm_review", name="Review", group="quality"),
        },
        edges=[],
    )

    context = context_manager.create_context(workflow_id=graph.workflow_id)
    execution_id = context.execution_id
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id=graph.workflow_id)
    records_manager.start_node_record(execution_id, "review", "llm_review")
    records_manager.complete_node_record(execution_id, "review", output_preview="done")
    context_manager.update_node_state(execution_id, "review", "SUCCEEDED")

    cards = service.build_node_cards(graph, execution_id)

    assert len(cards) == 1
    assert cards[0].task == "assessment"



def test_build_graph_view_returns_mermaid_text() -> None:
    service, graph, _ = prepare_execution()

    graph_view = service.build_graph_view(graph)

    assert graph_view.workflow_id == "sample_workflow"
    assert graph_view.workflow_name == "Sample Workflow"
    assert graph_view.mermaid_text.startswith("flowchart TD")
    assert "step1 --> step2" in graph_view.mermaid_text
    assert "step2 --> step3" in graph_view.mermaid_text



def test_build_execution_artifacts_view_returns_context_artifacts_and_outputs() -> None:
    service, _, execution_id = prepare_execution()

    artifacts_view = service.build_execution_artifacts_view(execution_id)

    assert artifacts_view.execution_id == execution_id
    assert artifacts_view.artifacts == {"final_report": {"path": "artifacts/final.md"}}
    assert set(artifacts_view.node_outputs.keys()) == {"step2", "step3"}
    assert artifacts_view.node_outputs["step3"]["count"] == 1
