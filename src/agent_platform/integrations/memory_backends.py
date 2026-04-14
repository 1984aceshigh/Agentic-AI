from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from agent_platform.integrations.memory_contracts import (
    MemoryQuery,
    MemoryRecord,
    MemoryStore,
    MemoryWriteRequest,
)


class InMemoryMemoryStore(MemoryStore):
    """Minimal in-memory backend for MemoryStore.

    This implementation is intentionally simple and non-persistent so the
    contract can be exercised before introducing SQLite or other backends.
    """

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def write(self, request: MemoryWriteRequest) -> MemoryRecord:
        record = MemoryRecord(
            record_id=str(uuid4()),
            scope=request.scope,
            workflow_id=request.workflow_id,
            execution_id=request.execution_id,
            tags=list(request.tags),
            content=dict(request.content),
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        self._records.append(record)
        return record

    def read(self, query: MemoryQuery) -> list[MemoryRecord]:
        matched = self._records

        if query.scope is not None:
            matched = [record for record in matched if record.scope == query.scope]

        if query.workflow_id is not None:
            matched = [
                record for record in matched if record.workflow_id == query.workflow_id
            ]

        if query.execution_id is not None:
            matched = [
                record
                for record in matched
                if record.execution_id == query.execution_id
            ]

        if query.tags:
            required_tags = set(query.tags)
            matched = [
                record
                for record in matched
                if required_tags.issubset(set(record.tags))
            ]

        matched = sorted(matched, key=lambda record: record.created_at, reverse=True)

        if query.limit <= 0:
            return []
        return matched[: query.limit]
