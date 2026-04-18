from __future__ import annotations

from pathlib import Path

from agent_platform.graph.builder import build_graph_model
from agent_platform.graph.mermaid import build_mermaid
from agent_platform.integrations import RAGDatasetService, RAGNodeBindingService
from agent_platform.models import GraphEdge, GraphModel, GraphNode, IssueSeverity
from agent_platform.runtime.context_manager import ExecutionContextManager
from agent_platform.runtime.app_config import load_runtime_llm_config
from agent_platform.runtime.execution_service import WorkflowExecutionService
from agent_platform.runtime.human_gate_service import HumanGateService
from agent_platform.runtime.records_manager import ExecutionRecordsManager
from agent_platform.ui_api import (
    ReadModelService,
    create_app,
)
from agent_platform.validators import has_errors, validate_workflow_spec
from agent_platform.workflow_definitions import DefinitionValidationService, FileWorkflowDefinitionRepository
from agent_platform.yaml_io.loader import load_workflow_yaml_text


def make_graph_model() -> GraphModel:
    return GraphModel(
        workflow_id="sample_workflow",
        workflow_name="Sample Workflow",
        start_node="step1",
        end_nodes=["step3"],
        direction="TD",
        nodes={
            "step1": GraphNode(id="step1", type="llm", name="Draft", group="analysis", config={"task": "generate"}),
            "step2": GraphNode(id="step2", type="human_gate", name="Human Review", group="review"),
            "step3": GraphNode(
                id="step3",
                type="llm",
                name="Knowledge Lookup",
                group="review",
                config={"task": "generate", "rag": {"profile": "default_rag", "query": "{{ input.question }}", "top_k": 5}},
            ),
        },
        edges=[
            GraphEdge(from_node="step1", to_node="step2"),
            GraphEdge(from_node="step2", to_node="step3"),
        ],
    )


def _build_definition_validation_service() -> DefinitionValidationService:
    def _validate(spec: object) -> list[str]:
        issues = validate_workflow_spec(spec)
        if not has_errors(issues):
            return []
        return [str(issue.message) for issue in issues if issue.severity is IssueSeverity.ERROR]

    return DefinitionValidationService(
        loader=load_workflow_yaml_text,
        validator=_validate,
        graph_builder=build_graph_model,
        mermaid_builder=build_mermaid,
    )


def _load_active_graphs(definition_root: Path) -> dict[str, GraphModel]:
    repository = FileWorkflowDefinitionRepository(definition_root)
    graphs: dict[str, GraphModel] = {}
    validation_service = _build_definition_validation_service()

    for meta in repository.list_active():
        document = repository.get(meta.workflow_id)
        validation = validation_service.validate_yaml_text(document.yaml_text)
        if not validation.is_valid or validation.graph is None:
            continue

        # pydantic model generated from graph builder
        graph = validation.graph
        graphs[str(graph.workflow_id)] = graph

    return graphs


class UIHumanGateServiceAdapter:
    def __init__(self, service: HumanGateService) -> None:
        self._service = service

    def approve_node(self, execution_id: str, node_id: str, comment: str | None = None) -> None:
        self._service.approve(execution_id=execution_id, node_id=node_id, comment=comment)

    def reject_node(
        self,
        execution_id: str,
        node_id: str,
        fallback_node_id: str | None = None,
        comment: str | None = None,
    ) -> None:
        self._service.reject(
            execution_id=execution_id,
            node_id=node_id,
            fallback_node_id=fallback_node_id,
            comment=comment,
        )


class UIRerunServiceAdapter:
    """UI route adapter that delegates rerun requests to execution service."""

    def __init__(self, execution_service: WorkflowExecutionService, records_manager: ExecutionRecordsManager) -> None:
        self._execution_service = execution_service
        self._records_manager = records_manager

    def rerun_from_node(self, execution_id: str, from_node_id: str) -> None:
        workflow_record = self._records_manager.get_workflow_record(execution_id)
        workflow_id = workflow_record.workflow_id

        self._execution_service.rerun_from_node(
            workflow_id=workflow_id,
            execution_id=execution_id,
            from_node_id=from_node_id,
        )


def build_app():
    project_root = Path(__file__).resolve().parents[1]
    definitions_root = project_root / "data" / "workflow_definitions"
    runtime_config_path = project_root / "config" / "runtime.yaml"
    runtime_llm_config = load_runtime_llm_config(runtime_config_path)

    workflow_graphs = _load_active_graphs(definitions_root)
    if not workflow_graphs:
        graph = make_graph_model()
        workflow_graphs = {graph.workflow_id: graph}

    context_manager = ExecutionContextManager()
    records_manager = ExecutionRecordsManager(
        storage_path=project_root / "data" / "runtime" / "execution_records.json"
    )
    rag_dataset_service = RAGDatasetService(
        catalog_path=project_root / "data" / "rag" / "datasets.json",
        datasets_dir=project_root / "data" / "rag" / "datasets",
        uploads_dir=project_root / "data" / "rag" / "uploads",
    )
    rag_node_binding_service = RAGNodeBindingService(
        bindings_path=project_root / "data" / "rag" / "node_bindings.json",
    )
    read_model_service = ReadModelService(
        context_manager=context_manager,
        records_manager=records_manager,
    )

    human_gate_core = HumanGateService(records_manager=records_manager, context_manager=context_manager)

    latest_execution_ids: dict[str, str | None] = {}
    execution_service = WorkflowExecutionService(
        context_manager=context_manager,
        records_manager=records_manager,
        workflow_graphs=workflow_graphs,
        latest_execution_ids=latest_execution_ids,
        openai_api_key=runtime_llm_config.openai_api_key,
        openai_model=runtime_llm_config.openai_model,
        llm_default_provider=runtime_llm_config.provider,
        rag_dataset_service=rag_dataset_service,
        rag_node_binding_service=rag_node_binding_service,
    )
    human_gate_service = UIHumanGateServiceAdapter(human_gate_core)
    rerun_service = UIRerunServiceAdapter(execution_service, records_manager)

    app = create_app(
        read_model_service=read_model_service,
        human_gate_service=human_gate_service,
        rerun_service=rerun_service,
        execution_service=execution_service,
        workflow_graphs=workflow_graphs,
        latest_execution_ids=latest_execution_ids,
        rag_dataset_service=rag_dataset_service,
        rag_node_binding_service=rag_node_binding_service,
    )
    return app


app = build_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)