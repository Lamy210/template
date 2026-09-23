from __future__ import annotations

from typing import Any
import re


SOURCE_WORKFLOW_NAME = "Release Build"
SOURCE_WORKFLOW_PATH = ".github/workflows/release-build.yml"
PUBLISHER_WORKFLOW_NAME = "Release Publisher"
PUBLISHER_WORKFLOW_PATH = ".github/workflows/release-publisher.yml"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _run_repository_errors(
    run: dict[str, Any],
    *,
    prefix: str,
    repository_id: int,
    repository_full_name: str,
) -> list[str]:
    errors: list[str] = []
    for field, label in (
        ("repository", "repository identity"),
        ("head_repository", "head repository identity"),
    ):
        value = run.get(field)
        if not isinstance(value, dict):
            errors.append(f"{prefix} {label} must be an object")
            continue
        if value.get("id") != repository_id or value.get("full_name") != repository_full_name:
            errors.append(f"{prefix} {label} does not match the audited repository")
    return errors


def _metadata_binding_errors(
    metadata: object,
    *,
    repository_full_name: str,
    source_run_id: int,
    source_run_attempt: int,
    source_sha: str,
    source_tag: str,
    publisher_run_id: int,
    publisher_run_attempt: int,
    publisher_sha: str,
) -> list[str]:
    if not isinstance(metadata, dict):
        return ["validator metadata must be a JSON object"]

    expected = {
        "sourceRepository": repository_full_name,
        "sourceRunId": source_run_id,
        "sourceRunAttempt": source_run_attempt,
        "sourceSHA": source_sha,
        "tag": source_tag,
        "publisherRunId": publisher_run_id,
        "publisherRunAttempt": publisher_run_attempt,
        "publisherSHA": publisher_sha,
    }
    errors: list[str] = []
    for field, expected_value in expected.items():
        if metadata.get(field) != expected_value:
            errors.append(f"{field} does not match runtime proof evidence")

    tag = metadata.get("tag")
    if not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None:
        errors.append("tag must match stable SemVer form vX.Y.Z")
    return errors


def _artifact_errors(
    artifacts: object,
    *,
    repository_id: int,
    publisher_run_id: int,
    publisher_run_attempt: int,
    publisher_sha: str,
    source_run_id: int,
    source_run_attempt: int,
) -> list[str]:
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
        return ["validator artifacts must be an array of objects"]

    expected_name = (
        f"validated-release-input-{publisher_run_id}-{publisher_run_attempt}-"
        f"{source_run_id}-{source_run_attempt}"
    )
    matches = [item for item in artifacts if item.get("name") == expected_name]
    if len(matches) != 1:
        return [
            "validator artifact must appear exactly once with expected publisher/source "
            f"run-attempt binding: {expected_name!r}; found {len(matches)}"
        ]

    artifact = matches[0]
    errors: list[str] = []
    if not _positive_int(artifact.get("id")):
        errors.append("validator artifact id must be a positive integer")
    if artifact.get("expired") is not False:
        errors.append("validator artifact must exist and not be expired")

    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict):
        errors.append("validator artifact workflow_run must be an object")
        return errors

    if workflow_run.get("id") != publisher_run_id:
        errors.append("validator artifact workflow_run.id does not match publisher run")
    if workflow_run.get("head_sha") != publisher_sha:
        errors.append("validator artifact workflow_run.head_sha does not match publisher SHA")
    if workflow_run.get("repository_id") != repository_id:
        errors.append("validator artifact repository_id does not match repository")
    if workflow_run.get("head_repository_id") != repository_id:
        errors.append("validator artifact head_repository_id does not match repository")
    return errors


def _ancestor_errors(
    comparison: object,
    *,
    source_sha: str,
) -> list[str]:
    if not isinstance(comparison, dict):
        return ["source/publisher comparison must be a JSON object"]

    errors: list[str] = []
    ahead_by = comparison.get("ahead_by")
    behind_by = comparison.get("behind_by")
    if (
        comparison.get("status") != "ahead"
        or type(ahead_by) is not int
        or ahead_by <= 0
        or type(behind_by) is not int
        or behind_by != 0
    ):
        errors.append("source SHA must be a strict ancestor of publisher SHA")

    base_commit = comparison.get("base_commit")
    if not isinstance(base_commit, dict) or base_commit.get("sha") != source_sha:
        errors.append("compare base_commit must equal source SHA")
    merge_base = comparison.get("merge_base_commit")
    if not isinstance(merge_base, dict) or merge_base.get("sha") != source_sha:
        errors.append("compare merge_base_commit must equal source SHA")
    return errors


def validate_post_split_runtime_proof(
    repository: object,
    default_commit: object,
    source_run: object,
    publisher_run: object,
    artifacts: object,
    metadata: object,
    comparison: object,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(repository, dict):
        return ["repository response must be a JSON object"]
    repository_id = repository.get("id")
    repository_full_name = repository.get("full_name")
    default_branch = repository.get("default_branch")
    if not _positive_int(repository_id):
        errors.append("repository id must be a positive integer")
    if not isinstance(repository_full_name, str) or "/" not in repository_full_name:
        errors.append("repository full_name must be in owner/repo form")
    if not isinstance(default_branch, str) or not default_branch:
        errors.append("repository default_branch must be a non-empty string")

    if not isinstance(source_run, dict):
        return errors + ["source run response must be a JSON object"]
    if not isinstance(publisher_run, dict):
        return errors + ["publisher run response must be a JSON object"]

    source_run_id = source_run.get("id")
    source_run_attempt = source_run.get("run_attempt")
    publisher_run_id = publisher_run.get("id")
    publisher_run_attempt = publisher_run.get("run_attempt")
    for value, label in (
        (source_run_id, "source run id"),
        (source_run_attempt, "source run attempt"),
        (publisher_run_id, "publisher run id"),
        (publisher_run_attempt, "publisher run attempt"),
    ):
        if not _positive_int(value):
            errors.append(f"{label} must be a positive integer")

    source_sha = source_run.get("head_sha")
    publisher_sha = publisher_run.get("head_sha")
    if not _sha(source_sha):
        errors.append("source run head SHA must be 40 lowercase hexadecimal characters")
    if not _sha(publisher_sha):
        errors.append("publisher run head SHA must be 40 lowercase hexadecimal characters")

    if source_run.get("name") != SOURCE_WORKFLOW_NAME:
        errors.append(f"source workflow name must equal {SOURCE_WORKFLOW_NAME!r}")
    if source_run.get("path") != SOURCE_WORKFLOW_PATH:
        errors.append(f"source workflow path must equal {SOURCE_WORKFLOW_PATH!r}")
    if source_run.get("event") != "push":
        errors.append("source event must equal 'push'")
    source_tag = source_run.get("head_branch")
    if not isinstance(source_tag, str) or TAG_RE.fullmatch(source_tag) is None:
        errors.append("source head_branch must match stable SemVer form vX.Y.Z")
    if source_run.get("status") != "completed" or source_run.get("conclusion") != "success":
        errors.append("source run must be completed successfully")

    if publisher_run.get("name") != PUBLISHER_WORKFLOW_NAME:
        errors.append(f"publisher workflow name must equal {PUBLISHER_WORKFLOW_NAME!r}")
    if publisher_run.get("path") != PUBLISHER_WORKFLOW_PATH:
        errors.append(f"publisher workflow path must equal {PUBLISHER_WORKFLOW_PATH!r}")
    if publisher_run.get("event") != "workflow_run":
        errors.append("publisher event must equal 'workflow_run'")
    if (
        isinstance(default_branch, str)
        and publisher_run.get("head_branch") != default_branch
    ):
        errors.append("publisher head_branch must equal repository default branch")

    if (
        _positive_int(repository_id)
        and isinstance(repository_full_name, str)
        and "/" in repository_full_name
    ):
        errors.extend(
            _run_repository_errors(
                source_run,
                prefix="source",
                repository_id=repository_id,
                repository_full_name=repository_full_name,
            )
        )
        errors.extend(
            _run_repository_errors(
                publisher_run,
                prefix="publisher",
                repository_id=repository_id,
                repository_full_name=repository_full_name,
            )
        )

    if _sha(source_sha) and _sha(publisher_sha) and source_sha == publisher_sha:
        errors.append("source SHA must differ from publisher SHA for post-split ancestor proof")

    if not isinstance(default_commit, dict) or not _sha(default_commit.get("sha")):
        errors.append("current default-branch commit response must contain a valid SHA")
    elif _sha(publisher_sha) and default_commit.get("sha") != publisher_sha:
        errors.append("publisher SHA must equal current default-branch head")

    if (
        _positive_int(repository_id)
        and _positive_int(source_run_id)
        and _positive_int(source_run_attempt)
        and _positive_int(publisher_run_id)
        and _positive_int(publisher_run_attempt)
        and _sha(publisher_sha)
    ):
        errors.extend(
            _artifact_errors(
                artifacts,
                repository_id=repository_id,
                publisher_run_id=publisher_run_id,
                publisher_run_attempt=publisher_run_attempt,
                publisher_sha=publisher_sha,
                source_run_id=source_run_id,
                source_run_attempt=source_run_attempt,
            )
        )

    if (
        isinstance(repository_full_name, str)
        and "/" in repository_full_name
        and _positive_int(source_run_id)
        and _positive_int(source_run_attempt)
        and _positive_int(publisher_run_id)
        and _positive_int(publisher_run_attempt)
        and _sha(source_sha)
        and isinstance(source_tag, str)
        and TAG_RE.fullmatch(source_tag) is not None
        and _sha(publisher_sha)
    ):
        errors.extend(
            _metadata_binding_errors(
                metadata,
                repository_full_name=repository_full_name,
                source_run_id=source_run_id,
                source_run_attempt=source_run_attempt,
                source_sha=source_sha,
                source_tag=source_tag,
                publisher_run_id=publisher_run_id,
                publisher_run_attempt=publisher_run_attempt,
                publisher_sha=publisher_sha,
            )
        )
        errors.extend(_ancestor_errors(comparison, source_sha=source_sha))

    return errors
