from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_platform.models import EdgeSpec, NodeInputSpec, WorkflowSpec


def make_minimal_workflow_payload() -> dict:
    return {
        "schema_version": "0.1",
        "workflow": {"id": "sample_workflow", "name": "Sample Workflow"},
        "runtime": {"start_node": "start", "end_nodes": ["end"]},
        "integrations": {},
        "nodes": [
            {"id": "start", "type": "llm_generate", "name": "Start"},
            {"id": "end", "type": "llm_review", "name": "End"},
        ],
        "edges": [{"from": "start", "to": "end"}],
    }


def test_workflow_spec_can_be_created_with_minimal_valid_data() -> None:
    spec = WorkflowSpec(**make_minimal_workflow_payload())
    assert spec.workflow.id == "sample_workflow"
    assert spec.runtime.start_node == "start"
    assert len(spec.nodes) == 2


def test_node_input_spec_accepts_from_alias() -> None:
    input_spec = NodeInputSpec(**{"from": [{"node": "previous", "key": "result"}]})
    assert input_spec.from_[0].node == "previous"
    assert input_spec.model_dump(by_alias=True) == {"from": [{"node": "previous", "key": "result"}]}


def test_edge_spec_accepts_from_and_to_aliases() -> None:
    edge = EdgeSpec(**{"from": "node_a", "to": "node_b"})
    assert edge.from_node == "node_a"
    assert edge.to_node == "node_b"
    assert edge.model_dump(by_alias=True) == {"from": "node_a", "to": "node_b"}


def test_workflow_spec_rejects_empty_nodes() -> None:
    payload = make_minimal_workflow_payload()
    payload["nodes"] = []

    with pytest.raises(ValidationError):
        WorkflowSpec(**payload)


def test_workflow_spec_rejects_empty_end_nodes() -> None:
    payload = make_minimal_workflow_payload()
    payload["runtime"]["end_nodes"] = []

    with pytest.raises(ValidationError):
        WorkflowSpec(**payload)
