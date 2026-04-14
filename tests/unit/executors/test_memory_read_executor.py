from __future__ import annotations

from agent_platform.executors import ExecutorRegistry, MemoryReadExecutor
from agent_platform.integrations import InMemoryMemoryStore, MemoryScope, MemoryWriteRequest


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
    }


def test_memory_read_executor_returns_records() -> None:
    store = InMemoryMemoryStore()
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.WORKFLOW,
            workflow_id="workflow_alpha",
            tags=["project_context"],
            content={"title": "A"},
        )
    )
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.WORKFLOW,
            workflow_id="workflow_alpha",
            tags=["project_context", "important"],
            content={"title": "B"},
        )
    )
    executor = MemoryReadExecutor(stores_by_profile_name={"default_memory": store})
    node = {
        "id": "read_memory",
        "type": "memory_read",
        "config": {
            "memory_profile": "default_memory",
            "scope": "workflow",
            "query": {"tags": ["project_context"], "limit": 5},
        },
    }

    result = executor.run(spec=_make_spec(), node=node, context=_make_context())

    assert result.status == "SUCCEEDED"
    assert result.output["count"] == 2
    assert result.output["scope"] == "workflow"
    assert result.output["tags"] == ["project_context"]
    assert result.output["records"][0]["content"]["title"] == "B"
    assert result.output["records"][1]["content"]["title"] == "A"


def test_memory_read_executor_fails_for_unknown_profile() -> None:
    executor = MemoryReadExecutor(stores_by_profile_name={})
    node = {
        "id": "read_memory",
        "type": "memory_read",
        "config": {
            "memory_profile": "missing_profile",
            "scope": "workflow",
            "query": {"tags": [], "limit": 5},
        },
    }

    result = executor.run(spec=_make_spec(), node=node, context=_make_context())

    assert result.status == "FAILED"
    assert "見つかりません" in (result.error_message or "")


def test_memory_read_executor_uses_execution_scope_filters() -> None:
    store = InMemoryMemoryStore()
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.EXECUTION,
            workflow_id="workflow_alpha",
            execution_id="execution_001",
            tags=["decision_log"],
            content={"title": "kept"},
        )
    )
    store.write(
        MemoryWriteRequest(
            scope=MemoryScope.EXECUTION,
            workflow_id="workflow_alpha",
            execution_id="execution_999",
            tags=["decision_log"],
            content={"title": "filtered_out"},
        )
    )
    executor = MemoryReadExecutor(stores_by_profile_name={"default_memory": store})
    node = {
        "id": "read_memory",
        "type": "memory_read",
        "config": {
            "memory_profile": "default_memory",
            "scope": "execution",
            "query": {"tags": ["decision_log"], "limit": 5},
        },
    }

    result = executor.run(spec=_make_spec(), node=node, context=_make_context())

    assert result.status == "SUCCEEDED"
    assert result.output["count"] == 1
    assert result.output["records"][0]["execution_id"] == "execution_001"


def test_memory_read_executor_can_be_registered() -> None:
    registry = ExecutorRegistry()
    executor = MemoryReadExecutor(stores_by_profile_name={"default_memory": InMemoryMemoryStore()})

    registry.register_executor(executor)

    assert registry.has("memory_read") is True
    assert registry.get("memory_read") is executor
