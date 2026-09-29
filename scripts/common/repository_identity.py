from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.common.repository_name import is_canonical_repository_name


@dataclass(frozen=True)
class RepositoryIdentity:
    repository_id: int
    full_name: str


def validate_repository_identity(
    document: Any,
    *,
    expected_repository: str,
) -> tuple[list[str], RepositoryIdentity | None]:
    errors: list[str] = []

    if not is_canonical_repository_name(expected_repository):
        errors.append("expected repository must use canonical owner/repo form")

    if not isinstance(document, dict):
        return errors + ["repository metadata must be a JSON object"], None

    repository_id = document.get("id")
    if type(repository_id) is not int or repository_id <= 0:
        errors.append("repository id must be a positive integer")

    full_name = document.get("full_name")
    if not is_canonical_repository_name(full_name):
        errors.append("repository full_name must use canonical owner/repo form")
    elif (
        is_canonical_repository_name(expected_repository)
        and full_name.casefold() != expected_repository.casefold()
    ):
        errors.append("repository full_name does not match expected repository")

    if errors:
        return errors, None

    assert isinstance(repository_id, int)
    assert isinstance(full_name, str)
    return [], RepositoryIdentity(repository_id=repository_id, full_name=full_name)
