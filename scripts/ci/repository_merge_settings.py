from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.common.repository_name import is_canonical_repository_name


@dataclass(frozen=True)
class RepositoryMergeSettings:
    repository_id: int
    full_name: str
    allow_squash_merge: bool
    allow_merge_commit: bool
    allow_rebase_merge: bool
    delete_branch_on_merge: bool


def validate_repository_merge_settings(
    document: Any,
    *,
    expected_repository: str,
) -> tuple[list[str], RepositoryMergeSettings | None]:
    errors: list[str] = []

    if not is_canonical_repository_name(expected_repository):
        errors.append("expected repository must use canonical owner/repo form")

    if not isinstance(document, dict):
        return ["repository metadata must be a JSON object"], None

    repository_id = document.get("id")
    if type(repository_id) is not int or repository_id <= 0:
        errors.append("repository id must be a positive integer")

    full_name = document.get("full_name")
    if (
        not isinstance(full_name, str)
        or not is_canonical_repository_name(full_name)
    ):
        errors.append("repository full_name must use canonical owner/repo form")
    elif (
        is_canonical_repository_name(expected_repository)
        and full_name.casefold() != expected_repository.casefold()
    ):
        errors.append(
            "repository full_name does not match the requested repository"
        )

    boolean_fields = (
        "allow_squash_merge",
        "allow_merge_commit",
        "allow_rebase_merge",
        "delete_branch_on_merge",
    )
    values: dict[str, bool] = {}
    for field in boolean_fields:
        value = document.get(field)
        if type(value) is not bool:
            errors.append(f"repository {field} must be a boolean")
        else:
            values[field] = value

    expected = {
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "delete_branch_on_merge": True,
    }
    for field, expected_value in expected.items():
        if field in values and values[field] is not expected_value:
            rendered = "true" if expected_value else "false"
            errors.append(f"repository {field} must equal {rendered}")

    if errors:
        return errors, None

    assert isinstance(repository_id, int)
    assert isinstance(full_name, str)
    return (
        [],
        RepositoryMergeSettings(
            repository_id=repository_id,
            full_name=full_name,
            allow_squash_merge=values["allow_squash_merge"],
            allow_merge_commit=values["allow_merge_commit"],
            allow_rebase_merge=values["allow_rebase_merge"],
            delete_branch_on_merge=values["delete_branch_on_merge"],
        ),
    )
