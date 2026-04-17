from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agent_platform.models import WorkflowSpec
from agent_platform.workflow_definitions.node_type_migration import normalize_workflow_node_types


class WorkflowLoaderError(Exception):
    def __init__(self, message: str, source: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.source = source


class WorkflowYamlParseError(WorkflowLoaderError):
    def __init__(
        self,
        message: str,
        source: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message=message, source=source)
        self.line = line
        self.column = column


class WorkflowModelValidationError(WorkflowLoaderError):
    def __init__(
        self,
        message: str,
        source: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message=message, source=source)
        self.errors = errors or []


class WorkflowFileReadError(WorkflowLoaderError):
    pass


def load_workflow_yaml(path: str | Path) -> WorkflowSpec:
    workflow_path = Path(path)
    source = str(workflow_path)

    try:
        text = workflow_path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError, UnicodeDecodeError) as exc:
        raise WorkflowFileReadError(
            message=f"Failed to read workflow YAML file: {source}",
            source=source,
        ) from exc

    try:
        return load_workflow_yaml_text(text)
    except WorkflowLoaderError as exc:
        exc.source = source
        raise


def load_workflow_yaml_text(text: str) -> WorkflowSpec:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        line: int | None = None
        column: int | None = None
        problem_mark = getattr(exc, "problem_mark", None)
        if problem_mark is not None:
            line = getattr(problem_mark, "line", None)
            column = getattr(problem_mark, "column", None)
            if line is not None:
                line += 1
            if column is not None:
                column += 1
        raise WorkflowYamlParseError(
            message=str(exc),
            line=line,
            column=column,
        ) from exc

    if data is None:
        data = {}

    if not isinstance(data, dict):
        raise WorkflowModelValidationError(
            message="WorkflowSpec validation failed",
            errors=[
                {
                    "type": "model_type",
                    "loc": (),
                    "msg": "Input should be a valid dictionary",
                    "input": data,
                }
            ],
        )

    return load_workflow_dict(data)


def load_workflow_dict(data: dict[str, Any]) -> WorkflowSpec:
    normalized_data, _ = normalize_workflow_node_types(data)
    try:
        return WorkflowSpec.model_validate(normalized_data)
    except ValidationError as exc:
        raise WorkflowModelValidationError(
            message="WorkflowSpec validation failed",
            errors=exc.errors(),
        ) from exc
