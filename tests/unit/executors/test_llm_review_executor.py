from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_platform.executors.llm_review import LLMReviewExecutor


@dataclass
class DummyContext:
    global_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class DummyNode:
    id: str
    type: str = "llm_review"
    config: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=dict)


def test_llm_review_executor_returns_dummy_review() -> None:
    executor = LLMReviewExecutor()
    context = DummyContext(node_outputs={"draft": {"outline_result": "sample"}})
    node = DummyNode(
        id="final_review",
        input={"from": [{"node": "draft", "key": "outline_result"}]},
    )

    result = executor.execute(context, node)

    assert result.status == "SUCCEEDED"
    assert result.output == {"review": "reviewed by final_review", "score": 80}
    assert result.error_message is None
    assert result.logs
