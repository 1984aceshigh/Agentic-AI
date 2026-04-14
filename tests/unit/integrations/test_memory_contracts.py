from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_platform.integrations.memory_contracts import (
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemoryStore,
    MemoryWriteRequest,
)


class DummyMemoryStore(MemoryStore):
    def read(self, query: MemoryQuery) -> list[MemoryRecord]:
        return [
            MemoryRecord(
                record_id="rec_1",
                scope=query.scope or MemoryScope.SHARED,
                workflow_id=query.workflow_id,
                execution_id=query.execution_id,
                tags=list(query.tags),
                content={"matched": True},
                created_at=datetime(2026, 4, 12, tzinfo=UTC),
            )
        ]

    def write(self, request: MemoryWriteRequest) -> MemoryRecord:
        return MemoryRecord(
            record_id="rec_written",
            scope=request.scope,
            workflow_id=request.workflow_id,
            execution_id=request.execution_id,
            tags=list(request.tags),
            content=dict(request.content),
            created_at=datetime(2026, 4, 12, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("member", "expected_value"),
    [
        (MemoryScope.EXECUTION, "execution"),
        (MemoryScope.WORKFLOW, "workflow"),
        (MemoryScope.SHARED, "shared"),
    ],
)
def test_memory_scope_enum_values(member: MemoryScope, expected_value: str) -> None:
    assert member.value == expected_value


def test_memory_record_can_be_created() -> None:
    now = datetime(2026, 4, 12, 9, 0, tzinfo=UTC)

    record = MemoryRecord(
        record_id="record_001",
        scope=MemoryScope.WORKFLOW,
        workflow_id="wf_001",
        execution_id=None,
        tags=["summary", "decision"],
        content={"text": "hello", "score": 1},
        created_at=now,
    )

    assert record.record_id == "record_001"
    assert record.scope is MemoryScope.WORKFLOW
    assert record.workflow_id == "wf_001"
    assert record.tags == ["summary", "decision"]
    assert record.content["text"] == "hello"
    assert record.created_at == now
    assert record.updated_at is None


def test_memory_query_can_be_created_with_defaults() -> None:
    query = MemoryQuery()

    assert query.scope is None
    assert query.workflow_id is None
    assert query.execution_id is None
    assert query.tags == []
    assert query.limit == 5


def test_memory_query_can_be_created_with_values() -> None:
    query = MemoryQuery(
        scope=MemoryScope.EXECUTION,
        workflow_id="wf_001",
        execution_id="exec_001",
        tags=["important"],
        limit=10,
    )

    assert query.scope is MemoryScope.EXECUTION
    assert query.workflow_id == "wf_001"
    assert query.execution_id == "exec_001"
    assert query.tags == ["important"]
    assert query.limit == 10


def test_memory_write_request_can_be_created() -> None:
    request = MemoryWriteRequest(
        scope=MemoryScope.SHARED,
        workflow_id=None,
        execution_id=None,
        tags=["kb"],
        content={"title": "note"},
    )

    assert request.scope is MemoryScope.SHARED
    assert request.tags == ["kb"]
    assert request.content == {"title": "note"}


def test_memory_store_is_abstract() -> None:
    with pytest.raises(TypeError):
        MemoryStore()


def test_concrete_memory_store_can_be_used() -> None:
    store = DummyMemoryStore()
    query = MemoryQuery(scope=MemoryScope.WORKFLOW, workflow_id="wf_002")

    records = store.read(query)

    assert len(records) == 1
    assert records[0].scope is MemoryScope.WORKFLOW
    assert records[0].workflow_id == "wf_002"


def test_concrete_memory_store_write_returns_memory_record() -> None:
    store = DummyMemoryStore()
    request = MemoryWriteRequest(
        scope=MemoryScope.EXECUTION,
        workflow_id="wf_003",
        execution_id="exec_003",
        tags=["checkpoint"],
        content={"status": "ok"},
    )

    record = store.write(request)

    assert isinstance(record, MemoryRecord)
    assert record.scope is MemoryScope.EXECUTION
    assert record.workflow_id == "wf_003"
    assert record.execution_id == "exec_003"
    assert record.tags == ["checkpoint"]
    assert record.content == {"status": "ok"}
