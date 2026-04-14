from __future__ import annotations

from agent_platform.models import IssueSeverity, ValidationIssue


def test_validation_issue_can_be_created() -> None:
    issue = ValidationIssue(
        code="missing_start_node",
        message="runtime.start_node is required",
        severity=IssueSeverity.ERROR,
    )
    assert issue.code == "missing_start_node"
    assert issue.severity is IssueSeverity.ERROR


def test_issue_severity_enum_values_match_expected_spec() -> None:
    assert [item.value for item in IssueSeverity] == ["ERROR", "WARNING"]
