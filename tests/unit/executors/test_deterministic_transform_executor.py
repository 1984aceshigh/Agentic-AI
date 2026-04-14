from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_platform.executors.deterministic_transform import DeterministicTransformExecutor


@dataclass
class DummyContext:
    global_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class DummyNode:
    id: str
    type: str = "deterministic_transform"
    config: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=dict)


def test_deterministic_transform_pass_through() -> None:
    executor = DeterministicTransformExecutor()
    context = DummyContext(node_outputs={"prev": {"payload": {"a": 1}}})
    node = DummyNode(
        id="transform",
        config={"transform_type": "pass_through"},
        input={"from": [{"node": "prev", "key": "payload"}]},
    )

    result = executor.execute(context, node)

    assert result.status == "SUCCEEDED"
    assert result.output == {"result": {"a": 1}}


def test_deterministic_transform_json_extract() -> None:
    executor = DeterministicTransformExecutor()
    context = DummyContext(node_outputs={"prev": {"payload": '{"title": "T", "summary": "S", "x": 1}'}})
    node = DummyNode(
        id="extract",
        config={
            "transform_type": "json_extract",
            "params": {"fields": ["title", "summary"]},
        },
        input={"from": [{"node": "prev", "key": "payload"}]},
    )

    result = executor.execute(context, node)

    assert result.status == "SUCCEEDED"
    assert result.output == {"result": {"title": "T", "summary": "S"}}


def test_deterministic_transform_merge_dict() -> None:
    executor = DeterministicTransformExecutor()
    context = DummyContext(
        node_outputs={
            "a": {"first": {"x": 1}},
            "b": {"second": {"y": 2}},
        }
    )
    node = DummyNode(
        id="merge",
        config={
            "transform_type": "merge_dict",
            "params": {"static_values": {"z": 3}},
        },
        input={
            "from": [
                {"node": "a", "key": "first"},
                {"node": "b", "key": "second"},
            ]
        },
    )

    result = executor.execute(context, node)

    assert result.status == "SUCCEEDED"
    assert result.output == {"result": {"x": 1, "y": 2, "z": 3}}


def test_deterministic_transform_template_render() -> None:
    executor = DeterministicTransformExecutor()
    context = DummyContext(
        global_inputs={"request": "Draft proposal"},
        node_outputs={"prev": {"payload": {"title": "My Title"}}},
    )
    node = DummyNode(
        id="render",
        config={
            "transform_type": "template_render",
            "params": {"template": "{title}: {request}"},
        },
        input={"from": [{"node": "prev", "key": "payload"}]},
    )

    result = executor.execute(context, node)

    assert result.status == "SUCCEEDED"
    assert result.output == {"result": "My Title: Draft proposal"}


def test_deterministic_transform_unknown_type_returns_failed_result() -> None:
    executor = DeterministicTransformExecutor()
    context = DummyContext()
    node = DummyNode(
        id="bad",
        config={"transform_type": "unknown_transform"},
    )

    result = executor.execute(context, node)

    assert result.status == "FAILED"
    assert result.error_message is not None
