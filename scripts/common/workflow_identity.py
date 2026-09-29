from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowIdentity:
    workflow_id: int
    path: str


def is_safe_workflow_filename(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value != value.strip() or "\n" in value or "\r" in value:
        return False
    if "/" in value or "\\" in value or value in {".", ".."}:
        return False
    return value.endswith((".yml", ".yaml"))


def validate_workflow_identity(
    document: Any,
    *,
    expected_workflow: str,
) -> tuple[list[str], WorkflowIdentity | None]:
    errors: list[str] = []

    if not is_safe_workflow_filename(expected_workflow):
        errors.append("expected workflow must be a safe .yml/.yaml file name")

    if not isinstance(document, dict):
        return errors + ["workflow metadata must be a JSON object"], None

    workflow_id = document.get("id")
    if type(workflow_id) is not int or workflow_id <= 0:
        errors.append("workflow id must be a positive integer")

    path = document.get("path")
    expected_path = (
        f".github/workflows/{expected_workflow}"
        if is_safe_workflow_filename(expected_workflow)
        else None
    )
    if not isinstance(path, str) or not path:
        errors.append("workflow path must be a non-empty string")
    elif path != path.strip() or "\n" in path or "\r" in path:
        errors.append("workflow path must be one canonical line")
    elif expected_path is not None and path != expected_path:
        errors.append("workflow path does not match expected workflow file")

    if errors:
        return errors, None

    assert isinstance(workflow_id, int)
    assert isinstance(path, str)
    return [], WorkflowIdentity(workflow_id=workflow_id, path=path)
