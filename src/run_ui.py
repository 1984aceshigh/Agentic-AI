from datetime import datetime, timezone

from agent_platform.models import ExecutionEvent, GraphEdge, GraphModel, GraphNode
from agent_platform.runtime.context_manager import ExecutionContextManager
from agent_platform.runtime.records_manager import ExecutionRecordsManager
from agent_platform.ui_api import (
    ReadModelService,
    create_app,
    set_latest_execution_ids,
    set_workflow_graphs,
)

UTC = timezone.utc


class FakeHumanGateService:
    def approve_node(self, execution_id: str, node_id: str, comment: str | None = None) -> None:
        pass

    def reject_node(
        self,
        execution_id: str,
        node_id: str,
        fallback_node_id: str | None = None,
        comment: str | None = None,
    ) -> None:
        pass


class FakeRerunService:
    def rerun_from_node(self, execution_id: str, from_node_id: str) -> None:
        pass


def make_graph_model() -> GraphModel:
    return GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step3"],
        direction="TD",
        nodes={
            "step1": GraphNode(id="step1", type="llm_generate", name="Draft", group="analysis"),
            "step2": GraphNode(id="step2", type="human_gate", name="Human Review", group="review"),
            "step3": GraphNode(id="step3", type="rag_retrieve", name="Knowledge Lookup", group="review"),
        },
        edges=[
            GraphEdge(from_node="step1", to_node="step2"),
            GraphEdge(from_node="step2", to_node="step3"),
        ],
    )


def build_app():
    graph = make_graph_model()
    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager()
    read_model_service = ReadModelService(
        context_manager=context_manager,
        records_manager=records_manager,
    )

    context = context_manager.create_context(workflow_id=graph.workflow_id)
    execution_id = context.execution_id
    records_manager.create_workflow_record(execution_id=execution_id, workflow_id=graph.workflow_id)

    records_manager.start_node_record(execution_id, "step1", "llm_generate")
    records_manager.complete_node_record(execution_id, "step1", output_preview="draft output")

    records_manager.start_node_record(execution_id, "step2", "human_gate")
    records_manager.mark_node_waiting_human(execution_id, "step2")

    records_manager.start_node_record(execution_id, "step3", "rag_retrieve")
    records_manager.fail_node_record(execution_id, "step3", error_message="retrieval failed")

    context_manager.update_node_state(execution_id, "step1", "SUCCEEDED")
    context_manager.update_node_state(execution_id, "step2", "WAITING_HUMAN")
    context_manager.update_node_state(execution_id, "step3", "FAILED")
    records_manager.set_workflow_status(execution_id, "FAILED")

    app = create_app(
        read_model_service=read_model_service,
        human_gate_service=FakeHumanGateService(),
        rerun_service=FakeRerunService(),
    )
    set_workflow_graphs(app, {graph.workflow_id: graph})
    set_latest_execution_ids(app, {graph.workflow_id: execution_id})
    return app


app = build_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)