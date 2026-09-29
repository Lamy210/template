from __future__ import annotations

import re

from scripts.common.repository_name import is_canonical_repository_name


SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _head_repository_identity(item: dict[str, object]) -> str | None:
    repository = item.get("headRepository")
    owner = item.get("headRepositoryOwner")

    if isinstance(repository, dict):
        name_with_owner = repository.get("nameWithOwner")
        if is_canonical_repository_name(name_with_owner):
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
            if is_canonical_repository_name(candidate):
                return candidate

    return None


def normalize_rest_pull_request_pages(
    document: object,
    *,
    expected_repository: str,
    expected_repository_id: int,
) -> tuple[list[str], list[dict[str, object]]]:
    errors: list[str] = []
    normalized: list[dict[str, object]] = []

    if not is_canonical_repository_name(expected_repository):
        return ["expected repository must be canonical owner/repo"], normalized
    if type(expected_repository_id) is not int or expected_repository_id <= 0:
        return ["expected repository id must be a positive integer"], normalized

    if not isinstance(document, list) or not document:
        return ["paginated pull request response must be a non-empty JSON array"], normalized

    expected_repository_key = expected_repository.lower()
    seen_numbers: set[int] = set()

    for page_index, page in enumerate(document):
        if not isinstance(page, list):
            errors.append(f"pull request page {page_index} must be a JSON array")
            continue

        for item_index, item in enumerate(page):
            label = f"pull request page {page_index} entry {item_index}"
            if not isinstance(item, dict):
                errors.append(f"{label} must be a JSON object")
                continue

            number = item.get("number")
            if type(number) is not int or number <= 0:
                errors.append(f"{label} has an invalid number")
                continue
            if number in seen_numbers:
                errors.append(f"duplicate pull request number across pages: {number}")
                continue
            seen_numbers.add(number)

            if item.get("state") != "open":
                errors.append(f"{label} is not open")
                continue

            head = item.get("head")
            base = item.get("base")
            if not isinstance(head, dict) or not isinstance(base, dict):
                errors.append(f"{label} is missing head/base metadata")
                continue

            head_ref = head.get("ref")
            head_sha = head.get("sha")
            base_ref = base.get("ref")
            if not isinstance(head_ref, str) or not head_ref or "\n" in head_ref:
                errors.append(f"{label} has an invalid head ref")
                continue
            if not isinstance(base_ref, str) or not base_ref or "\n" in base_ref:
                errors.append(f"{label} has an invalid base ref")
                continue
            if not isinstance(head_sha, str) or SHA_RE.fullmatch(head_sha) is None:
                errors.append(f"{label} has an invalid head commit")
                continue

            head_repository = head.get("repo")
            base_repository = base.get("repo")
            if not isinstance(head_repository, dict):
                errors.append(f"{label} has no head repository")
                continue
            if not isinstance(base_repository, dict):
                errors.append(f"{label} has no base repository")
                continue

            head_full_name = head_repository.get("full_name")
            base_full_name = base_repository.get("full_name")
            head_repository_id = head_repository.get("id")
            base_repository_id = base_repository.get("id")
            if not is_canonical_repository_name(head_full_name):
                errors.append(f"{label} has an invalid head repository identity")
                continue
            if not is_canonical_repository_name(base_full_name):
                errors.append(f"{label} has an invalid base repository identity")
                continue
            if type(base_repository_id) is not int or base_repository_id <= 0:
                errors.append(f"{label} has an invalid base repository id")
                continue
            if type(head_repository_id) is not int or head_repository_id <= 0:
                errors.append(f"{label} has an invalid head repository id")
                continue
            if base_full_name.lower() != expected_repository_key:
                errors.append(f"{label} targets an unexpected base repository")
                continue
            if base_repository_id != expected_repository_id:
                errors.append(f"{label} targets an unexpected base repository id")
                continue

            same_head_repository = (
                head_full_name.lower() == expected_repository_key
            )
            if same_head_repository and head_repository_id != expected_repository_id:
                errors.append(
                    f"{label} same-repository head has an unexpected repository id"
                )
                continue
            if (
                not same_head_repository
                and head_repository_id == expected_repository_id
            ):
                errors.append(
                    f"{label} foreign head name reuses the expected repository id"
                )
                continue

            head_owner, head_name = head_full_name.split("/", 1)
            normalized.append(
                {
                    "number": number,
                    "headRefName": head_ref,
                    "baseRefName": base_ref,
                    "headRefOid": head_sha,
                    "headRepository": {
                        "name": head_name,
                        "nameWithOwner": head_full_name,
                        "databaseId": head_repository_id,
                    },
                    "headRepositoryOwner": {"login": head_owner},
                    "baseRepository": {
                        "nameWithOwner": base_full_name,
                        "databaseId": base_repository_id,
                    },
                    "isCrossRepository": not same_head_repository,
                }
            )

    return errors, normalized


def select_same_repository_pull_request(
    document: object,
    *,
    expected_repository: str,
    expected_repository_id: int,
    expected_head: str,
    expected_base: str,
    expected_head_sha: str,
) -> tuple[list[str], int | None]:
    errors: list[str] = []

    expected_repository_key: str | None = None
    if not is_canonical_repository_name(expected_repository):
        errors.append("expected repository must be canonical owner/repo")
    else:
        expected_repository_key = expected_repository.lower()
    if type(expected_repository_id) is not int or expected_repository_id <= 0:
        errors.append("expected repository id must be a positive integer")
    if not isinstance(expected_head, str) or not expected_head or "\n" in expected_head:
        errors.append("expected head branch must be a non-empty single line")
    if not isinstance(expected_base, str) or not expected_base or "\n" in expected_base:
        errors.append("expected base branch must be a non-empty single line")
    if (
        not isinstance(expected_head_sha, str)
        or SHA_RE.fullmatch(expected_head_sha) is None
    ):
        errors.append("expected head commit must be 40 lowercase hexadecimal characters")

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

        head_repository_document = item.get("headRepository")
        base_repository_document = item.get("baseRepository")
        head_repository_id = (
            head_repository_document.get("databaseId")
            if isinstance(head_repository_document, dict)
            else None
        )
        base_repository_name = (
            base_repository_document.get("nameWithOwner")
            if isinstance(base_repository_document, dict)
            else None
        )
        base_repository_id = (
            base_repository_document.get("databaseId")
            if isinstance(base_repository_document, dict)
            else None
        )
        if type(head_repository_id) is not int or head_repository_id <= 0:
            errors.append(f"pull request entry {index} has invalid head repository id")
            continue
        if not is_canonical_repository_name(base_repository_name):
            errors.append(f"pull request entry {index} has invalid base repository identity")
            continue
        if type(base_repository_id) is not int or base_repository_id <= 0:
            errors.append(f"pull request entry {index} has invalid base repository id")
            continue
        if (
            expected_repository_key is not None
            and base_repository_name.lower() != expected_repository_key
        ):
            errors.append(f"pull request entry {index} targets an unexpected base repository")
            continue
        if base_repository_id != expected_repository_id:
            errors.append(f"pull request entry {index} targets an unexpected base repository id")
            continue

        head_ref_oid = item.get("headRefOid")
        if not isinstance(head_ref_oid, str) or SHA_RE.fullmatch(head_ref_oid) is None:
            errors.append(f"pull request entry {index} has an invalid head commit")
            continue

        is_cross_repository = item.get("isCrossRepository")
        if (
            expected_repository_key is not None
            and head_repository.lower() == expected_repository_key
        ):
            if head_repository_id != expected_repository_id:
                errors.append(
                    f"pull request entry {index} same-repository head has an unexpected repository id"
                )
            if is_cross_repository is not False:
                errors.append(
                    f"pull request entry {index} claims cross-repository identity for the tap repository"
                )
            if head_ref_oid != expected_head_sha:
                errors.append(
                    f"pull request entry {index} does not point to the pushed automation commit"
                )
            if (
                type(number) is int
                and number > 0
                and is_cross_repository is False
                and head_repository_id == expected_repository_id
                and head_ref_oid == expected_head_sha
            ):
                candidates.append(number)
        else:
            if head_repository_id == expected_repository_id:
                errors.append(
                    f"pull request entry {index} foreign head name reuses the expected repository id"
                )
            if is_cross_repository is not True:
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
