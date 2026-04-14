from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class IssueSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    code: str
    message: str
    severity: IssueSeverity
    location: str | None = None
    related_node_id: str | None = None
    suggestion: str | None = None
