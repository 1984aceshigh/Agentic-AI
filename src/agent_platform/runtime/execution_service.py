from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

from agent_platform.executors import (
    DeterministicTransformExecutor,
    ExecutorRegistry,
    HumanGateExecutor,
    LLMGenerateExecutor,
    LLMReviewExecutor,
    MemoryReadExecutor,
    MemoryWriteExecutor,
    RAGRetrieveExecutor,
)
from agent_platform.graph import compile_langgraph
from agent_platform.integrations import DummyEchoLLMAdapter, OpenAIChatCompletionAdapter
from agent_platform.runtime.events import (
    NODE_STATUS_FAILED,
    NODE_STATUS_RUNNING,
    NODE_STATUS_SUCCEEDED,
    NODE_STATUS_WAITING_HUMAN,
    WORKFLOW_STATUS_FAILED,
    WORKFLOW_STATUS_RUNNING,
    WORKFLOW_STATUS_SUCCEEDED,
    WORKFLOW_STATUS_WAITING_HUMAN,
)
from agent_platform.runtime.rerun import RerunService


class WorkflowExecutionService:
    """Execute GraphModel workflows and persist runtime/UI state."""

    def __init__(
        self,
        *,
        context_manager: Any,
        records_manager: Any,
        workflow_graphs: dict[str, Any],
        latest_execution_ids: dict[str, str | None],
        executor_registry: ExecutorRegistry | None = None,
        rerun_service: RerunService | None = None,
        openai_api_key: str | None = None,
        openai_model: str | None = None,
        llm_default_provider: str | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._records_manager = records_manager
        self._workflow_graphs = workflow_graphs
        self._latest_execution_ids = latest_execution_ids
        self._openai_api_key = openai_api_key
        self._openai_model = openai_model
        self._llm_default_provider = llm_default_provider
        self._registry = executor_registry or self._build_default_registry()
        self._rerun_service = rerun_service or RerunService(context_manager, records_manager)

    def run_workflow(self, workflow_id: str, *, global_inputs: dict[str, Any] | None = None) -> str:
        graph = self._workflow_graphs.get(workflow_id)
        if graph is None:
            raise KeyError(f"Unknown workflow_id: {workflow_id}")

        context = self._context_manager.create_context(workflow_id=workflow_id, global_inputs=global_inputs or {})
        execution_id = context.execution_id
        self._records_manager.create_workflow_record(execution_id=execution_id, workflow_id=workflow_id)
        self._latest_execution_ids[workflow_id] = execution_id

        self._invoke_graph(graph=graph, execution_id=execution_id)
        return execution_id

    def rerun_from_node(self, *, workflow_id: str, execution_id: str, from_node_id: str) -> str:
        graph = self._workflow_graphs.get(workflow_id)
        if graph is None:
            raise KeyError(f"Unknown workflow_id: {workflow_id}")

        self._rerun_service.prepare_rerun(execution_id, graph, from_node_id)
        from_node_type = str(getattr(graph.nodes[from_node_id].type, "value", graph.nodes[from_node_id].type))
        self._records_manager.start_node_record(execution_id, from_node_id, from_node_type)
        self._context_manager.update_node_state(execution_id, from_node_id, NODE_STATUS_RUNNING)
        self._records_manager.append_node_log(execution_id, from_node_id, "rerun requested from ui")
        self._records_manager.set_workflow_status(execution_id, WORKFLOW_STATUS_RUNNING)
        self._latest_execution_ids[workflow_id] = execution_id
        return execution_id

    def _invoke_graph(self, *, graph: Any, execution_id: str) -> None:
        compiled = compile_langgraph(graph, node_fn_factory=self._make_node_fn)
        context = self._context_manager.get_context(execution_id)
        state = {
            "execution_id": execution_id,
            "workflow_id": graph.workflow_id,
            "node_states": dict(context.node_states),
            "node_outputs": dict(context.node_outputs),
            "logs": list(context.metadata.get("logs", []) if isinstance(context.metadata, dict) else []),
            "halted": False,
        }
        final_state = compiled.invoke(state)
        self._context_manager.set_artifact(execution_id, "langgraph_final_state", final_state)
        self._finalize_workflow_status(execution_id)

    def _make_node_fn(self, graph_node: Any):
        def _fn(state: dict[str, Any]) -> dict[str, Any]:
            if state.get("halted"):
                return {}

            execution_id = str(state.get("execution_id") or "")
            if not execution_id:
                raise ValueError("execution_id is required in LangGraph state")

            context = self._context_manager.get_context(execution_id)
            node_id = graph_node.id
            node_type = str(getattr(graph_node.type, "value", graph_node.type))
            node_obj = SimpleNamespace(
                id=node_id,
                type=node_type,
                config=dict(getattr(graph_node, "config", {}) or {}),
                input=dict(getattr(graph_node, "input", {}) or {}),
            )

            self._records_manager.start_node_record(execution_id, node_id, node_type)
            self._context_manager.update_node_state(execution_id, node_id, "RUNNING")
            self._set_adapter_info(execution_id, node_id, node_obj)

            executor = self._registry.resolve_for_node(node_obj)
            result = executor.run(spec=None, node=node_obj, context=context)

            for log in result.logs:
                self._records_manager.append_node_log(execution_id, node_id, log)
                self._context_manager.append_log(execution_id, f"{node_id}: {log}")

            if result.input_preview is not None:
                self._records_manager.set_node_input_preview(
                    execution_id,
                    node_id,
                    result.input_preview,
                )

            if result.output:
                self._context_manager.set_node_output(execution_id, node_id, result.output)

            if result.status == NODE_STATUS_WAITING_HUMAN:
                self._records_manager.mark_node_waiting_human(execution_id, node_id)
                self._context_manager.update_node_state(execution_id, node_id, NODE_STATUS_WAITING_HUMAN)
                node_state = NODE_STATUS_WAITING_HUMAN
                halted = True
            elif result.status == NODE_STATUS_SUCCEEDED:
                self._context_manager.update_node_state(execution_id, node_id, NODE_STATUS_SUCCEEDED)
                self._records_manager.complete_node_record(
                    execution_id,
                    node_id,
                    output_preview=self._build_output_preview(
                        output=result.output,
                        fallback_summary=result.summary or executor.summarize_output(result.output),
                    ),
                )
                node_state = NODE_STATUS_SUCCEEDED
                halted = False
            else:
                self._context_manager.update_node_state(execution_id, node_id, NODE_STATUS_FAILED)
                self._records_manager.fail_node_record(
                    execution_id,
                    node_id,
                    error_message=result.error_message or "executor failed",
                )
                node_state = NODE_STATUS_FAILED
                halted = True

            updated: dict[str, Any] = {
                "node_states": {node_id: node_state},
                "logs": [f"{node_id}: {log}" for log in result.logs],
            }
            if result.output:
                updated["node_outputs"] = {node_id: result.output}
            if halted:
                updated["halted"] = True
            return updated

        return _fn

    def _finalize_workflow_status(self, execution_id: str) -> None:
        context = self._context_manager.get_context(execution_id)
        statuses = set(context.node_states.values())
        if NODE_STATUS_FAILED in statuses:
            status = WORKFLOW_STATUS_FAILED
        elif NODE_STATUS_WAITING_HUMAN in statuses:
            status = WORKFLOW_STATUS_WAITING_HUMAN
        else:
            status = WORKFLOW_STATUS_SUCCEEDED
        self._records_manager.set_workflow_status(execution_id, status)

    def _set_adapter_info(self, execution_id: str, node_id: str, node: Any) -> None:
        config = getattr(node, "config", {}) or {}
        adapter_ref = config.get("adapter_ref")
        connection_ref = config.get("connection_ref")
        contract = config.get("contract")
        resolved_capabilities = config.get("required_capabilities") or []
        if not isinstance(resolved_capabilities, list):
            resolved_capabilities = []
        self._records_manager.set_node_adapter_info(
            execution_id,
            node_id,
            adapter_ref=str(adapter_ref) if adapter_ref else None,
            contract=str(contract) if contract else None,
            connection_ref=str(connection_ref) if connection_ref else None,
            resolved_capabilities=[str(item) for item in resolved_capabilities],
        )

    def _build_output_preview(self, *, output: dict[str, Any], fallback_summary: str | None) -> str | None:
        if not isinstance(output, dict) or not output:
            return fallback_summary

        for key in ("result", "review", "text"):
            value = output.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
            return str(value)

        return fallback_summary

    def _build_default_registry(self) -> ExecutorRegistry:
        openai_api_key = self._openai_api_key if self._openai_api_key is not None else os.getenv("OPENAI_API_KEY")
        openai_model = self._openai_model if self._openai_model is not None else os.getenv("OPENAI_MODEL")
        if openai_model is None:
            openai_model = "gpt-4o-mini"

        default_provider = (
            self._llm_default_provider
            if self._llm_default_provider is not None
            else os.getenv("AGENT_PLATFORM_LLM_PROVIDER", "dummy")
        ).strip().lower()

        openai_adapter = OpenAIChatCompletionAdapter(api_key=openai_api_key, model=openai_model)
        dummy_adapter = DummyEchoLLMAdapter()
        default_adapter = openai_adapter if default_provider == "openai" else dummy_adapter

        registry = ExecutorRegistry()
        registry.register(
            "llm_generate",
            LLMGenerateExecutor(
                adapters_by_provider={
                    "openai": openai_adapter,
                    "dummy": dummy_adapter,
                },
                default_adapter=default_adapter,
            ),
        )
        registry.register(
            "llm_review",
            LLMReviewExecutor(
                adapters_by_provider={
                    "openai": openai_adapter,
                    "dummy": dummy_adapter,
                },
                default_adapter=default_adapter,
            ),
        )
        registry.register("human_gate", HumanGateExecutor())
        registry.register("deterministic_transform", DeterministicTransformExecutor())
        registry.register("memory_read", MemoryReadExecutor())
        registry.register("memory_write", MemoryWriteExecutor())
        registry.register("rag_retrieve", RAGRetrieveExecutor())
        return registry
