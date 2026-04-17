from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_platform.executors.llm import LLMExecutor
from agent_platform.integrations.rag_backends import InMemoryVectorRetriever
from agent_platform.integrations.rag_contracts import DocumentChunk


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
