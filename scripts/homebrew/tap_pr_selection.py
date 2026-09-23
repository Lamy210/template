from __future__ import annotations

import re


REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _head_repository_identity(item: dict[str, object]) -> str | None:
    repository = item.get("headRepository")
    owner = item.get("headRepositoryOwner")

    if isinstance(repository, dict):
        name_with_owner = repository.get("nameWithOwner")
        if isinstance(name_with_owner, str) and REPOSITORY_RE.fullmatch(name_with_owner):
            return name_with_owner

        name = repository.get("name")
        login = owner.get("login") if isinstance(owner, dict) else None
        if (
            isinstance(name, str)
            and isinstance(login, str)
            and name not in {".", ".."}
            and login not in {".", ".."}
        ):
            candidate = f"{login}/{name}"
            if REPOSITORY_RE.fullmatch(candidate):
                return candidate

    return None


def select_same_repository_pull_request(
    document: object,
    *,
    expected_repository: str,
    expected_head: str,
    expected_base: str,
) -> tuple[list[str], int | None]:
    errors: list[str] = []

    if not isinstance(expected_repository, str) or REPOSITORY_RE.fullmatch(expected_repository) is None:
        errors.append("expected repository must be in owner/repo form")
    if not isinstance(expected_head, str) or not expected_head or "\n" in expected_head:
        errors.append("expected head branch must be a non-empty single line")
    if not isinstance(expected_base, str) or not expected_base or "\n" in expected_base:
        errors.append("expected base branch must be a non-empty single line")

    if not isinstance(document, list):
        errors.append("pull request query result must be a JSON array")
        return errors, None

    candidates: list[int] = []
    for index, item in enumerate(document):
        if not isinstance(item, dict):
            errors.append(f"pull request entry {index} must be a JSON object")
            continue

        number = item.get("number")
        if type(number) is not int or number <= 0:
            errors.append(f"pull request entry {index} has an invalid number")

        if item.get("headRefName") != expected_head:
            errors.append(f"pull request entry {index} has unexpected head branch")
        if item.get("baseRefName") != expected_base:
            errors.append(f"pull request entry {index} has unexpected base branch")

        head_repository = _head_repository_identity(item)
        if head_repository is None:
            errors.append(f"pull request entry {index} has invalid head repository identity")
            continue

        is_cross_repository = item.get("isCrossRepository")
        if head_repository == expected_repository:
            if is_cross_repository is not False:
                errors.append(
                    f"pull request entry {index} claims cross-repository identity for the tap repository"
                )
            if type(number) is int and number > 0:
                candidates.append(number)
        elif is_cross_repository is not True:
            errors.append(
                f"pull request entry {index} has a foreign head repository without cross-repository identity"
            )

    if len(candidates) > 1:
        errors.append(
            "more than one open same-repository pull request matches the automation branch"
        )
        return errors, None

    if errors:
        return errors, None
    return errors, candidates[0] if candidates else None
