from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_platform.executors.llm import LLMExecutor
from agent_platform.integrations.rag_backends import InMemoryVectorRetriever
from agent_platform.integrations.rag_contracts import DocumentChunk


class _BrokenAdapter:
    def complete(self, request):
        raise RuntimeError("adapter unavailable")


class _CaptureAdapter:
    def __init__(self) -> None:
        self.last_request = None

    def complete(self, request):
        self.last_request = request
        return type("Resp", (), {"text": "company_name: ACME", "raw": {}})()


@dataclass
class DummyContext:
    workflow_id: str = "wf-1"
    execution_id: str = "exec-1"
    global_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class DummyNode:
    id: str
    type: str = "llm"
    config: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=dict)


def test_llm_executor_retrieves_rag_from_prompt_when_query_not_explicit() -> None:
    retriever = InMemoryVectorRetriever(
        chunks=[
            DocumentChunk(chunk_id="c1", document_id="d1", text="credit workflow guideline"),
            DocumentChunk(chunk_id="c2", document_id="d2", text="unrelated topic"),
        ]
    )
    executor = LLMExecutor(retrievers_by_profile_name={"kb": retriever})
    context = DummyContext(global_inputs={"user_question": "credit workflow"})
    node = DummyNode(
        id="llm_1",
        config={
            "task": "generate",
            "prompt": "Answer about {{ global.user_question }}",
            "input_definition": "domain: finance",
            "rag": {
                "profile": "kb",
                "top_k": 1,
            },
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert "rag" in result.output
    assert result.output["rag"]["count"] == 1
    assert "RAG context:" in (result.input_preview or "")


def test_llm_executor_assessment_task_outputs_review_key() -> None:
    executor = LLMExecutor()
    context = DummyContext()
    node = DummyNode(
        id="llm_2",
        config={
            "task": "assessment",
            "prompt": "Assess this draft",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert "review" in result.output
    assert "assessment_content" in result.output
    assert result.output["assessment_content"] == result.output["review"]
    assert "result" not in result.output
    assert result.output.get("task") == "assessment"


def test_llm_executor_assessment_sets_selected_option_and_next_node() -> None:
    executor = LLMExecutor()
    context = DummyContext()
    node = DummyNode(
        id="llm_3",
        config={
            "task": "assessment",
            "prompt": "Assess this draft",
            "assessment_options": ["pass", "rework"],
            "assessment_routes": {"pass": "publish", "rework": "rewrite"},
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("selected_option") in {"pass", "rework"}
    assert result.output.get("next_node") in {"publish", "rewrite"}


def test_llm_executor_extract_outputs_structured_payload() -> None:
    executor = LLMExecutor()
    context = DummyContext()
    node = DummyNode(
        id="llm_4",
        config={
            "task": "extract",
            "prompt": "company_name: ACME\ninvoice_no: INV-1001",
            "extract_fields": ["company_name", "invoice_no"],
            "extract_output_format": "yaml",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("task") == "extract"
    assert result.output.get("extract_output_format") == "yaml"
    assert result.output.get("extracted", {}).get("company_name") == "ACME"
    assert "invoice_no" in result.output.get("result", "")


def test_llm_executor_returns_failed_when_adapter_raises() -> None:
    executor = LLMExecutor(default_adapter=_BrokenAdapter())
    context = DummyContext()
    node = DummyNode(
        id="llm_fail",
        config={
            "task": "generate",
            "prompt": "hello",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "FAILED"
    assert result.error_message == "adapter unavailable"


def test_llm_executor_extract_respects_configured_output_format() -> None:
    adapter = _CaptureAdapter()
    executor = LLMExecutor(default_adapter=adapter)
    context = DummyContext()
    node = DummyNode(
        id="llm_extract_fmt",
        config={
            "task": "extract",
            "prompt": "company_name: ACME",
            "extract_fields": ["company_name"],
            "extract_output_format": "markdown",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("extract_output_format") == "markdown"
    assert "- **company_name**:" in result.output.get("result", "")


def test_llm_executor_assessment_defaults_temperature_to_zero() -> None:
    adapter = _CaptureAdapter()
    executor = LLMExecutor(default_adapter=adapter)
    context = DummyContext()
    node = DummyNode(
        id="llm_assess_temp",
        config={
            "task": "assessment",
            "prompt": "Assess",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert adapter.last_request is not None
    assert adapter.last_request.temperature == 0.0


def test_llm_executor_assessment_routes_match_case_insensitive_keys() -> None:
    executor = LLMExecutor()
    context = DummyContext()
    node = DummyNode(
        id="llm_assessment_bool_route",
        config={
            "task": "assessment",
            "prompt": "False",
            "assessment_options": ["False", "True"],
            "assessment_routes": {"false": "node_false", "true": "node_true"},
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("selected_option") == "False"
    assert result.output.get("next_node") == "node_false"


def test_llm_executor_generate_supports_markdown_json_output_format() -> None:
    adapter = _CaptureAdapter()
    adapter.complete = lambda request: type("Resp", (), {"text": '{"status": "ok"}', "raw": {}})()  # type: ignore[method-assign]
    executor = LLMExecutor(default_adapter=adapter)
    context = DummyContext()
    node = DummyNode(
        id="llm_generate_md_json",
        config={
            "task": "generate",
            "prompt": "Generate json",
            "output_format": "markdown_json",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("output_format") == "markdown_json"
    assert result.output.get("result", "").startswith("```json\n")
    assert result.output.get("structured_result") == {"status": "ok"}


def test_llm_executor_markdown_mermaid_does_not_double_wrap_when_already_fenced() -> None:
    adapter = _CaptureAdapter()
    mermaid_text = "```mermaid\nworkflow TD\n  A --> B\n```"
    adapter.complete = lambda request: type("Resp", (), {"text": mermaid_text, "raw": {}})()  # type: ignore[method-assign]
    executor = LLMExecutor(default_adapter=adapter)
    context = DummyContext()
    node = DummyNode(
        id="llm_generate_md_mermaid",
        config={
            "task": "generate",
            "prompt": "Generate mermaid",
            "output_format": "markdown_mermaid",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("result") == "```mermaid\nflowchart TD\n  A --> B\n```"


def test_llm_executor_markdown_mermaid_extracts_block_from_mixed_text() -> None:
    adapter = _CaptureAdapter()
    mixed_text = "Here is diagram\n```mermaid\nworkflow TD\n  A --> B\n```\nthanks"
    adapter.complete = lambda request: type("Resp", (), {"text": mixed_text, "raw": {}})()  # type: ignore[method-assign]
    executor = LLMExecutor(default_adapter=adapter)
    context = DummyContext()
    node = DummyNode(
        id="llm_generate_md_mermaid_mixed",
        config={
            "task": "generate",
            "prompt": "Generate mermaid",
            "output_format": "markdown_mermaid",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("result") == "```mermaid\nflowchart TD\n  A --> B\n```"


def test_llm_executor_markdown_mermaid_unwraps_nested_markdown_mermaid_fence() -> None:
    adapter = _CaptureAdapter()
    nested = "```mermaid\n```markdown_mermaid\nworkflow TD\n  A --> B\n```\n```"
    adapter.complete = lambda request: type("Resp", (), {"text": nested, "raw": {}})()  # type: ignore[method-assign]
    executor = LLMExecutor(default_adapter=adapter)
    context = DummyContext()
    node = DummyNode(
        id="llm_generate_md_mermaid_nested",
        config={
            "task": "generate",
            "prompt": "Generate mermaid",
            "output_format": "markdown_mermaid",
        },
    )

    result = executor.run(spec=None, node=node, context=context)

    assert result.status == "SUCCEEDED"
    assert result.output.get("result") == "```mermaid\nflowchart TD\n  A --> B\n```"
