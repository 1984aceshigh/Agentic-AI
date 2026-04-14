from __future__ import annotations

from agent_platform.executors import ExecutorRegistry, MemoryWriteExecutor
from agent_platform.integrations import InMemoryMemoryStore, MemoryQuery, MemoryScope


def _make_spec() -> dict:
    return {
        "integrations": {
            "memory_profiles": {
                "default_memory": {
                    "backend": "in_memory",
                    "contract": "memory_store",
                }
            }
        }
    }


def _make_context() -> dict:
    return {
        "workflow_id": "workflow_alpha",
        "execution_id": "execution_001",
        "upstream": {"note": "from context"},
    }


def test_memory_write_executor_writes_record() -> None:
    store = InMemoryMemoryStore()
    executor = MemoryWriteExecutor(stores_by_profile_name={"default_memory": store})
    node = {
        "id": "write_memory",
        "type": "memory_write",
        "config": {
            "memory_profile": "default_memory",
            "scope": "workflow",
            "tags": ["decision_log", "approved"],
            "content_template": {"message": "saved"},
        },
    }

    result = executor.run(spec=_make_spec(), node=node, context=_make_context())

    assert result.status == "SUCCEEDED"
    assert result.output["scope"] == "workflow"
    assert result.output["tags"] == ["decision_log", "approved"]
    records = store.read(
        MemoryQuery(
            scope=MemoryScope.WORKFLOW,
            workflow_id="workflow_alpha",
            tags=["decision_log"],
            limit=5,
        )
    )
    assert len(records) == 1
    assert records[0].content == {"message": "saved"}


def test_memory_write_executor_reflects_execution_scope() -> None:
    store = InMemoryMemoryStore()
    executor = MemoryWriteExecutor(stores_by_profile_name={"default_memory": store})
    node = {
        "id": "write_memory",
        "type": "memory_write",
        "config": {
            "memory_profile": "default_memory",
            "scope": "execution",
            "tags": ["decision_log"],
            "content_template": {"message": "saved"},
        },
    }

    result = executor.run(spec=_make_spec(), node=node, context=_make_context())

    assert result.status == "SUCCEEDED"
    records = store.read(
        MemoryQuery(
            scope=MemoryScope.EXECUTION,
            workflow_id="workflow_alpha",
            execution_id="execution_001",
            tags=["decision_log"],
            limit=5,
        )
    )
    assert len(records) == 1
    assert records[0].execution_id == "execution_001"


def test_memory_write_executor_fails_for_unknown_profile() -> None:
    executor = MemoryWriteExecutor(stores_by_profile_name={})
    node = {
        "id": "write_memory",
        "type": "memory_write",
        "config": {
            "memory_profile": "missing_profile",
            "scope": "workflow",
            "tags": ["decision_log"],
            "content_template": {"message": "saved"},
        },
    }

    result = executor.run(spec=_make_spec(), node=node, context=_make_context())

    assert result.status == "FAILED"
    assert "見つかりません" in (result.error_message or "")


def test_memory_write_executor_can_be_registered() -> None:
    registry = ExecutorRegistry()
    executor = MemoryWriteExecutor(stores_by_profile_name={"default_memory": InMemoryMemoryStore()})

    registry.register_executor(executor)

    assert registry.has("memory_write") is True
    assert registry.get("memory_write") is executor
