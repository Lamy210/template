from __future__ import annotations

import re


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def canonical_validated_artifact_name(
    publisher_run_id: int,
    publisher_run_attempt: int,
    source_run_id: int,
    source_run_attempt: int,
) -> str:
    return (
        f"validated-release-input-{publisher_run_id}-{publisher_run_attempt}-"
        f"{source_run_id}-{source_run_attempt}"
    )


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def verify_validated_artifact(
    *,
    artifact_metadata: object,
    artifact_id: int,
    artifact_name: str,
    artifact_digest: str,
    publisher_run_id: int,
    publisher_run_attempt: int,
    publisher_sha: str,
    repository_id: int,
    source_run_id: int,
    source_run_attempt: int,
) -> list[str]:
    errors: list[str] = []

    integer_fields = (
        ("artifact ID", artifact_id),
        ("publisher run ID", publisher_run_id),
        ("publisher run attempt", publisher_run_attempt),
        ("repository ID", repository_id),
        ("source run ID", source_run_id),
        ("source run attempt", source_run_attempt),
    )
    for label, value in integer_fields:
        if not _is_positive_int(value):
            errors.append(f"{label} must be a positive integer")

    if not isinstance(publisher_sha, str) or SHA_RE.fullmatch(publisher_sha) is None:
        errors.append("publisher SHA must be 40 lowercase hexadecimal characters")

    if not isinstance(artifact_digest, str) or DIGEST_RE.fullmatch(artifact_digest) is None:
        errors.append("validated artifact digest must use sha256:<64 lowercase hex>")

    canonical_name = ""
    canonical_identity = (
        publisher_run_id,
        publisher_run_attempt,
        source_run_id,
        source_run_attempt,
    )
    if all(_is_positive_int(value) for value in canonical_identity):
        canonical_name = canonical_validated_artifact_name(*canonical_identity)
        if artifact_name != canonical_name:
            errors.append(
                "validated artifact name must equal canonical current publisher-attempt name "
                f"{canonical_name}"
            )
    elif not isinstance(artifact_name, str) or not artifact_name:
        errors.append("validated artifact name must be a non-empty string")

    if not isinstance(artifact_metadata, dict):
        errors.append("validated artifact API metadata must be a JSON object")
        return errors

    metadata_id = artifact_metadata.get("id")
    if not _is_positive_int(metadata_id) or metadata_id != artifact_id:
        errors.append("validated artifact API identity mismatch")

    metadata_name = artifact_metadata.get("name")
    if not canonical_name or metadata_name != canonical_name:
        errors.append("validated artifact API name does not match current publisher attempt")

    if artifact_metadata.get("expired") is not False:
        errors.append("validated artifact is expired or has invalid expiration state")

    metadata_digest = artifact_metadata.get("digest")
    if not isinstance(metadata_digest, str) or DIGEST_RE.fullmatch(metadata_digest) is None:
        errors.append("validated artifact API digest is missing or malformed")
    elif metadata_digest != artifact_digest:
        errors.append("validated artifact API digest mismatch")

    workflow_run = artifact_metadata.get("workflow_run")
    if not isinstance(workflow_run, dict):
        errors.append("validated artifact workflow_run metadata is missing")
    else:
        workflow_run_id = workflow_run.get("id")
        if not _is_positive_int(workflow_run_id) or workflow_run_id != publisher_run_id:
            errors.append("validated artifact does not belong to the current publisher run")

        workflow_repository_id = workflow_run.get("repository_id")
        if not _is_positive_int(workflow_repository_id) or workflow_repository_id != repository_id:
            errors.append("validated artifact repository ID does not match the current repository")

        workflow_head_repository_id = workflow_run.get("head_repository_id")
        if (
            not _is_positive_int(workflow_head_repository_id)
            or workflow_head_repository_id != repository_id
        ):
            errors.append("validated artifact head repository ID does not match the current repository")

        workflow_head_sha = workflow_run.get("head_sha")
        if not isinstance(workflow_head_sha, str) or SHA_RE.fullmatch(workflow_head_sha) is None:
            errors.append("validated artifact publisher head SHA is missing or malformed")
        elif workflow_head_sha != publisher_sha:
            errors.append("validated artifact publisher head SHA mismatch")

    return errors
