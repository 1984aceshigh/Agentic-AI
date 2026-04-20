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
    assert result.input_preview == "human_gate task=approval"
    assert result.output == {
        "human_gate_task": "approval",
        "pending_input": {"outline_result": "draft"},
        "required_fields": [],
        "allow_files": False,
        "instructions": None,
        "approval_options": ["承認", "否認"],
    }


def test_human_gate_executor_entry_input_task_sets_required_fields_and_allow_files() -> None:
    executor = HumanGateExecutor()
    context = DummyContext()
    node = DummyNode(
        id="entry",
        config={
            "task": "entry_input",
            "required_fields": ["input_file", "priority"],
            "instructions": "Upload input file",
        },
    )

    result = executor.execute(context, node)

    assert result.status == "WAITING_HUMAN"
    assert result.requires_human_action is True
    assert result.output["human_gate_task"] == "entry_input"
    assert result.output["required_fields"] == ["input_file", "priority"]
    assert result.output["allow_files"] is True
    assert result.output["instructions"] == "Upload input file"
    assert result.output["approval_options"] == []
    assert result.input_preview == "human_gate task=entry_input, required_fields=input_file, priority"


def test_human_gate_executor_approval_task_uses_custom_approval_options() -> None:
    executor = HumanGateExecutor()
    context = DummyContext()
    node = DummyNode(
        id="approve",
        config={
            "task": "approval",
            "approval_options": ["go", "hold"],
        },
    )

    result = executor.execute(context, node)

    assert result.status == "WAITING_HUMAN"
    assert result.output["approval_options"] == ["go", "hold"]
