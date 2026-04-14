from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_platform.executors.human_gate import HumanGateExecutor


@dataclass
class DummyContext:
    global_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class DummyNode:
    id: str
    type: str = "human_gate"
    config: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=dict)


def test_human_gate_executor_returns_waiting_human() -> None:
    executor = HumanGateExecutor()
    context = DummyContext(node_outputs={"prev": {"outline_result": "draft"}})
    node = DummyNode(
        id="human_review",
        input={"from": [{"node": "prev", "key": "outline_result"}]},
    )

    result = executor.execute(context, node)

    assert result.status == "WAITING_HUMAN"
    assert result.requires_human_action is True
    assert result.error_message is None
    assert result.output == {"pending_input": {"outline_result": "draft"}}
