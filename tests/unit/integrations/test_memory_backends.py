from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from agent_platform.integrations.memory_backends import InMemoryMemoryStore
from agent_platform.integrations.memory_contracts import (
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemoryWriteRequest,
)


def test_write_returns_memory_record() -> None:
    store = InMemoryMemoryStore()

    record = store.write(
        MemoryWriteRequest(
            scope=MemoryScope.WORKFLOW,
            workflow_id="wf_001",
            execution_id=None,
            tags=["summary", "draft"],
            content={"text": "hello"},
        )
    )

    assert isinstance(record, MemoryRecord)
    assert record.scope is MemoryScope.WORKFLOW
    assert record.workflow_id == "wf_001"
    assert record.execution_id is None
    assert record.tags == ["summary", "draft"]
    assert record.content == {"text": "hello"}
    assert record.updated_at is None
    UUID(record.record_id)


def test_read_returns_written_record() -> None:
    store = InMemoryMemoryStore()
    written = store.write(
        MemoryWriteRequest(
            scope=MemoryScope.SHARED,
            tags=["knowledge"],
            content={"title": "note"},
        )
    )

    records = store.read(MemoryQuery())

    assert len(records) == 1
    assert records[0].record_id == written.record_id


def test_read_filters_by_scope() -> None:
    store = InMemoryMemoryStore()
    store.write(MemoryWriteRequest(scope=MemoryScope.EXECUTION, content={"v": 1}))
    store.write(MemoryWriteRequest(scope=MemoryScope.WORKFLOW, content={"v": 2}))

    records = store.read(MemoryQuery(scope=MemoryScope.WORKFLOW))

    assert len(records) == 1
    assert records[0].scope is MemoryScope.WORKFLOW
    assert records[0].content == {"v": 2}


def test_read_filters_by_workflow_id() -> None:
    store = InMemoryMemoryStore()
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.WORKFLOW,
            workflow_id="wf_a",
            content={"v": "a"},
        )
    )
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.WORKFLOW,
            workflow_id="wf_b",
            content={"v": "b"},
        )
    )

    records = store.read(MemoryQuery(workflow_id="wf_b"))

    assert len(records) == 1
    assert records[0].workflow_id == "wf_b"
    assert records[0].content == {"v": "b"}


def test_read_filters_by_execution_id() -> None:
    store = InMemoryMemoryStore()
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.EXECUTION,
            execution_id="exec_a",
            content={"v": "a"},
        )
    )
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.EXECUTION,
            execution_id="exec_b",
            content={"v": "b"},
        )
    )

    records = store.read(MemoryQuery(execution_id="exec_a"))

    assert len(records) == 1
    assert records[0].execution_id == "exec_a"
    assert records[0].content == {"v": "a"}


def test_read_filters_by_tags_using_all_elements() -> None:
    store = InMemoryMemoryStore()
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.SHARED,
            tags=["a", "b", "c"],
            content={"match": "yes"},
        )
    )
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.SHARED,
            tags=["a"],
            content={"match": "no"},
        )
    )

    records = store.read(MemoryQuery(tags=["a", "b"]))

    assert len(records) == 1
    assert records[0].content == {"match": "yes"}


def test_read_applies_limit() -> None:
    store = InMemoryMemoryStore()
    for index in range(3):
        store.write(
            MemoryWriteRequest(
                scope=MemoryScope.SHARED,
                content={"index": index},
            )
        )

    records = store.read(MemoryQuery(limit=2))

    assert len(records) == 2


def test_read_returns_newest_first() -> None:
    store = InMemoryMemoryStore()
    older = store.write(
        MemoryWriteRequest(scope=MemoryScope.SHARED, content={"name": "older"})
    )
    newer = store.write(
        MemoryWriteRequest(scope=MemoryScope.SHARED, content={"name": "newer"})
    )

    store._records = [
        older.model_copy(update={"created_at": datetime(2026, 4, 12, 9, 0, tzinfo=UTC)}),
        newer.model_copy(update={"created_at": datetime(2026, 4, 12, 9, 5, tzinfo=UTC)}),
    ]

    records = store.read(MemoryQuery(limit=5))

    assert [record.content["name"] for record in records] == ["newer", "older"]


def test_read_combines_filters() -> None:
    store = InMemoryMemoryStore()
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.WORKFLOW,
            workflow_id="wf_001",
            tags=["decision", "approved"],
            content={"id": 1},
        )
    )
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.WORKFLOW,
            workflow_id="wf_001",
            tags=["decision"],
            content={"id": 2},
        )
    )
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.SHARED,
            workflow_id="wf_001",
            tags=["decision", "approved"],
            content={"id": 3},
        )
    )

    records = store.read(
        MemoryQuery(
            scope=MemoryScope.WORKFLOW,
            workflow_id="wf_001",
            tags=["decision", "approved"],
            limit=5,
        )
    )

    assert len(records) == 1
    assert records[0].content == {"id": 1}


def test_read_with_non_positive_limit_returns_empty_list() -> None:
    store = InMemoryMemoryStore()
    store.write(MemoryWriteRequest(scope=MemoryScope.SHARED, content={"x": 1}))

    assert store.read(MemoryQuery(limit=0)) == []
