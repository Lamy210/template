#!/usr/bin/env python3
"""Build deterministic evidence from a validated post-split runtime proof."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

TOP_LEVEL_FIELDS = {
    "ancestor",
    "application",
    "defaultHead",
    "proofType",
    "publisher",
    "repository",
    "schemaVersion",
    "source",
}
ANCESTOR_FIELDS = {"aheadBy", "behindBy", "mergeBaseSHA", "status"}
APPLICATION_FIELDS = {"appBasename", "bundleId", "version"}
DEFAULT_HEAD_FIELDS = {"finalSHA", "initialSHA"}
PUBLISHER_FIELDS = {
    "runAttempt",
    "runId",
    "sha",
    "validatorArtifactDigest",
    "validatorArtifactId",
    "workflowName",
    "workflowPath",
}
REPOSITORY_FIELDS = {"defaultBranch", "fullName", "id"}
SOURCE_FIELDS = {
    "archiveDigest",
    "artifactDigest",
    "artifactId",
    "runAttempt",
    "runId",
    "sha",
    "tag",
    "workflowName",
    "workflowPath",
}

SOURCE_WORKFLOW_NAME = "Release Build"
SOURCE_WORKFLOW_PATH = ".github/workflows/release-build.yml"
PUBLISHER_WORKFLOW_NAME = "Release Publisher"
PUBLISHER_WORKFLOW_PATH = ".github/workflows/release-publisher.yml"


class EvidenceError(ValueError):
    pass


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise EvidenceError(f"{label} must be a positive integer")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be a non-empty string")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} must be 40 lowercase hexadecimal characters")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise EvidenceError(f"{label} must use sha256:<64 lowercase hex>")
    return value


def _validator_artifact(
    artifacts: object,
    *,
    publisher_run_id: int,
    publisher_run_attempt: int,
    source_run_id: int,
    source_run_attempt: int,
) -> dict[str, Any]:
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
        raise EvidenceError("validator artifacts must be an array of objects")

    expected_name = (
        f"validated-release-input-{publisher_run_id}-{publisher_run_attempt}-"
        f"{source_run_id}-{source_run_attempt}"
    )
    matches = [item for item in artifacts if item.get("name") == expected_name]
    if len(matches) != 1:
        raise EvidenceError(
            f"expected exactly one validator artifact named {expected_name!r}"
        )
    return matches[0]


def build_evidence(
    *,
    repository: object,
    default_commit: object,
    final_default_commit: object,
    source_run: object,
    publisher_run: object,
    artifacts: object,
    metadata: object,
    archive_digest: object,
    comparison: object,
) -> dict[str, object]:
    repo = _object(repository, "repository")
    initial_head = _object(default_commit, "initial default-branch commit")
    final_head = _object(final_default_commit, "final default-branch commit")
    source = _object(source_run, "source run")
    publisher = _object(publisher_run, "publisher run")
    validated_metadata = _object(metadata, "validator metadata")
    relation = _object(comparison, "source/publisher comparison")

    repository_id = _positive_int(repo.get("id"), "repository id")
    repository_full_name = _string(repo.get("full_name"), "repository full_name")
    if REPOSITORY_RE.fullmatch(repository_full_name) is None:
        raise EvidenceError("repository full_name must be owner/repo")
    default_branch = _string(repo.get("default_branch"), "repository default_branch")

    source_run_id = _positive_int(source.get("id"), "source run id")
    source_run_attempt = _positive_int(source.get("run_attempt"), "source run attempt")
    source_sha = _sha(source.get("head_sha"), "source SHA")
    source_tag = _string(source.get("head_branch"), "source tag")
    if TAG_RE.fullmatch(source_tag) is None:
        raise EvidenceError("source tag must be canonical stable SemVer")

    publisher_run_id = _positive_int(publisher.get("id"), "publisher run id")
    publisher_run_attempt = _positive_int(
        publisher.get("run_attempt"), "publisher run attempt"
    )
    publisher_sha = _sha(publisher.get("head_sha"), "publisher SHA")

    initial_head_sha = _sha(initial_head.get("sha"), "initial default-head SHA")
    final_head_sha = _sha(final_head.get("sha"), "final default-head SHA")
    if initial_head_sha != publisher_sha or final_head_sha != publisher_sha:
        raise EvidenceError("default-head snapshots must equal publisher SHA")

    artifact = _validator_artifact(
        artifacts,
        publisher_run_id=publisher_run_id,
        publisher_run_attempt=publisher_run_attempt,
        source_run_id=source_run_id,
        source_run_attempt=source_run_attempt,
    )
    validator_artifact_id = _positive_int(
        artifact.get("id"), "validator artifact id"
    )
    validator_artifact_digest = _digest(
        artifact.get("digest"), "validator artifact digest"
    )

    source_artifact_id = _positive_int(
        validated_metadata.get("sourceArtifactId"), "source artifact id"
    )
    source_artifact_digest = _digest(
        validated_metadata.get("sourceArtifactDigest"), "source artifact digest"
    )
    unsigned_archive_digest = _digest(archive_digest, "unsigned archive digest")
    if validated_metadata.get("archiveSha256") != unsigned_archive_digest:
        raise EvidenceError("validator metadata archive digest does not match proof input")

    app_basename = _string(validated_metadata.get("appBasename"), "app basename")
    bundle_id = _string(validated_metadata.get("bundleId"), "bundle id")
    version = _string(validated_metadata.get("version"), "application version")

    ahead_by = _positive_int(relation.get("ahead_by"), "compare ahead_by")
    behind_by = relation.get("behind_by")
    if type(behind_by) is not int or behind_by != 0:
        raise EvidenceError("compare behind_by must equal zero")
    if relation.get("status") != "ahead":
        raise EvidenceError("compare status must equal 'ahead'")
    merge_base = _object(relation.get("merge_base_commit"), "compare merge_base_commit")
    merge_base_sha = _sha(merge_base.get("sha"), "compare merge-base SHA")
    if merge_base_sha != source_sha:
        raise EvidenceError("compare merge-base SHA must equal source SHA")

    return {
        "ancestor": {
            "aheadBy": ahead_by,
            "behindBy": behind_by,
            "mergeBaseSHA": merge_base_sha,
            "status": "ahead",
        },
        "application": {
            "appBasename": app_basename,
            "bundleId": bundle_id,
            "version": version,
        },
        "defaultHead": {
            "finalSHA": final_head_sha,
            "initialSHA": initial_head_sha,
        },
        "proofType": "post-split-ancestor-runtime",
        "publisher": {
            "runAttempt": publisher_run_attempt,
            "runId": publisher_run_id,
            "sha": publisher_sha,
            "validatorArtifactDigest": validator_artifact_digest,
            "validatorArtifactId": validator_artifact_id,
            "workflowName": _string(publisher.get("name"), "publisher workflow name"),
            "workflowPath": _string(publisher.get("path"), "publisher workflow path"),
        },
        "repository": {
            "defaultBranch": default_branch,
            "fullName": repository_full_name,
            "id": repository_id,
        },
        "schemaVersion": 2,
        "source": {
            "archiveDigest": unsigned_archive_digest,
            "artifactDigest": source_artifact_digest,
            "artifactId": source_artifact_id,
            "runAttempt": source_run_attempt,
            "runId": source_run_id,
            "sha": source_sha,
            "tag": source_tag,
            "workflowName": _string(source.get("name"), "source workflow name"),
            "workflowPath": _string(source.get("path"), "source workflow path"),
        },
    }


def _closed_object_errors(
    value: object,
    *,
    label: str,
    expected_fields: set[str],
) -> tuple[list[str], dict[str, Any] | None]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"], None

    errors: list[str] = []
    fields = set(value)
    missing = sorted(expected_fields - fields)
    unexpected = sorted(fields - expected_fields)
    if missing:
        errors.append(f"{label} missing fields: {missing!r}")
    if unexpected:
        errors.append(f"{label} unexpected fields: {unexpected!r}")
    return errors, value


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _is_safe_app_basename(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and value.endswith(".app")
    )


def validate_evidence_document(document: object) -> list[str]:
    errors, root = _closed_object_errors(
        document,
        label="evidence",
        expected_fields=TOP_LEVEL_FIELDS,
    )
    if root is None:
        return errors

    schema_version = root.get("schemaVersion")
    if type(schema_version) is not int or schema_version != 2:
        errors.append("schemaVersion must equal integer 2")
    if root.get("proofType") != "post-split-ancestor-runtime":
        errors.append("proofType must equal 'post-split-ancestor-runtime'")

    repository_errors, repository = _closed_object_errors(
        root.get("repository"),
        label="repository",
        expected_fields=REPOSITORY_FIELDS,
    )
    errors.extend(repository_errors)
    if repository is not None:
        if not _is_positive_int(repository.get("id")):
            errors.append("repository.id must be a positive integer")
        full_name = repository.get("fullName")
        if not isinstance(full_name, str) or REPOSITORY_RE.fullmatch(full_name) is None:
            errors.append("repository.fullName must be owner/repo")
        default_branch = repository.get("defaultBranch")
        if (
            not isinstance(default_branch, str)
            or not default_branch
            or "\n" in default_branch
            or "\r" in default_branch
        ):
            errors.append("repository.defaultBranch must be a non-empty single-line string")

    default_head_errors, default_head = _closed_object_errors(
        root.get("defaultHead"),
        label="defaultHead",
        expected_fields=DEFAULT_HEAD_FIELDS,
    )
    errors.extend(default_head_errors)
    if default_head is not None:
        for field in ("initialSHA", "finalSHA"):
            value = default_head.get(field)
            if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
                errors.append(
                    f"defaultHead.{field} must be 40 lowercase hexadecimal characters"
                )

    source_errors, source = _closed_object_errors(
        root.get("source"),
        label="source",
        expected_fields=SOURCE_FIELDS,
    )
    errors.extend(source_errors)
    if source is not None:
        for field in ("runId", "runAttempt", "artifactId"):
            if not _is_positive_int(source.get(field)):
                errors.append(f"source.{field} must be a positive integer")
        source_sha = source.get("sha")
        if not isinstance(source_sha, str) or SHA_RE.fullmatch(source_sha) is None:
            errors.append("source.sha must be 40 lowercase hexadecimal characters")
        source_tag = source.get("tag")
        if not isinstance(source_tag, str) or TAG_RE.fullmatch(source_tag) is None:
            errors.append("source.tag must match stable SemVer form vX.Y.Z")
        for field in ("artifactDigest", "archiveDigest"):
            value = source.get(field)
            if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
                errors.append(f"source.{field} must use sha256:<64 lowercase hex>")
        if source.get("workflowName") != SOURCE_WORKFLOW_NAME:
            errors.append(f"source.workflowName must equal {SOURCE_WORKFLOW_NAME!r}")
        if source.get("workflowPath") != SOURCE_WORKFLOW_PATH:
            errors.append(f"source.workflowPath must equal {SOURCE_WORKFLOW_PATH!r}")

    publisher_errors, publisher = _closed_object_errors(
        root.get("publisher"),
        label="publisher",
        expected_fields=PUBLISHER_FIELDS,
    )
    errors.extend(publisher_errors)
    if publisher is not None:
        for field in ("runId", "runAttempt", "validatorArtifactId"):
            if not _is_positive_int(publisher.get(field)):
                errors.append(f"publisher.{field} must be a positive integer")
        publisher_sha = publisher.get("sha")
        if not isinstance(publisher_sha, str) or SHA_RE.fullmatch(publisher_sha) is None:
            errors.append("publisher.sha must be 40 lowercase hexadecimal characters")
        digest = publisher.get("validatorArtifactDigest")
        if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
            errors.append(
                "publisher.validatorArtifactDigest must use sha256:<64 lowercase hex>"
            )
        if publisher.get("workflowName") != PUBLISHER_WORKFLOW_NAME:
            errors.append(
                f"publisher.workflowName must equal {PUBLISHER_WORKFLOW_NAME!r}"
            )
        if publisher.get("workflowPath") != PUBLISHER_WORKFLOW_PATH:
            errors.append(
                f"publisher.workflowPath must equal {PUBLISHER_WORKFLOW_PATH!r}"
            )

    application_errors, application = _closed_object_errors(
        root.get("application"),
        label="application",
        expected_fields=APPLICATION_FIELDS,
    )
    errors.extend(application_errors)
    if application is not None:
        if not _is_safe_app_basename(application.get("appBasename")):
            errors.append("application.appBasename must be a safe .app basename")
        bundle_id = application.get("bundleId")
        if not isinstance(bundle_id, str) or not bundle_id:
            errors.append("application.bundleId must be a non-empty string")
        version = application.get("version")
        if not isinstance(version, str) or TAG_RE.fullmatch(f"v{version}") is None:
            errors.append("application.version must match stable SemVer form X.Y.Z")

    ancestor_errors, ancestor = _closed_object_errors(
        root.get("ancestor"),
        label="ancestor",
        expected_fields=ANCESTOR_FIELDS,
    )
    errors.extend(ancestor_errors)
    if ancestor is not None:
        if ancestor.get("status") != "ahead":
            errors.append("ancestor.status must equal 'ahead'")
        if not _is_positive_int(ancestor.get("aheadBy")):
            errors.append("ancestor.aheadBy must be a positive integer")
        behind_by = ancestor.get("behindBy")
        if type(behind_by) is not int or behind_by != 0:
            errors.append("ancestor.behindBy must equal integer 0")
        merge_base_sha = ancestor.get("mergeBaseSHA")
        if not isinstance(merge_base_sha, str) or SHA_RE.fullmatch(merge_base_sha) is None:
            errors.append(
                "ancestor.mergeBaseSHA must be 40 lowercase hexadecimal characters"
            )

    if source is not None and publisher is not None:
        source_sha = source.get("sha")
        publisher_sha = publisher.get("sha")
        if (
            isinstance(source_sha, str)
            and SHA_RE.fullmatch(source_sha) is not None
            and isinstance(publisher_sha, str)
            and SHA_RE.fullmatch(publisher_sha) is not None
            and source_sha == publisher_sha
        ):
            errors.append("source.sha must differ from publisher.sha")

        if (
            _is_positive_int(source.get("runId"))
            and _is_positive_int(publisher.get("runId"))
            and source.get("runId") == publisher.get("runId")
        ):
            errors.append("source.runId must differ from publisher.runId")

        if (
            _is_positive_int(source.get("artifactId"))
            and _is_positive_int(publisher.get("validatorArtifactId"))
            and source.get("artifactId") == publisher.get("validatorArtifactId")
        ):
            errors.append(
                "source.artifactId must differ from publisher.validatorArtifactId"
            )

    if default_head is not None and publisher is not None:
        publisher_sha = publisher.get("sha")
        if (
            isinstance(publisher_sha, str)
            and SHA_RE.fullmatch(publisher_sha) is not None
        ):
            for field in ("initialSHA", "finalSHA"):
                value = default_head.get(field)
                if (
                    isinstance(value, str)
                    and SHA_RE.fullmatch(value) is not None
                    and value != publisher_sha
                ):
                    errors.append(f"defaultHead.{field} must equal publisher.sha")

    if source is not None and ancestor is not None:
        source_sha = source.get("sha")
        merge_base_sha = ancestor.get("mergeBaseSHA")
        if (
            isinstance(source_sha, str)
            and SHA_RE.fullmatch(source_sha) is not None
            and isinstance(merge_base_sha, str)
            and SHA_RE.fullmatch(merge_base_sha) is not None
            and merge_base_sha != source_sha
        ):
            errors.append("ancestor.mergeBaseSHA must equal source.sha")

    if source is not None and application is not None:
        tag = source.get("tag")
        version = application.get("version")
        if (
            isinstance(tag, str)
            and TAG_RE.fullmatch(tag) is not None
            and isinstance(version, str)
            and version != tag[1:]
        ):
            errors.append("source.tag and application.version are inconsistent")

    return errors


def write_evidence(path: Path, evidence: dict[str, object]) -> None:
    errors = validate_evidence_document(evidence)
    if errors:
        raise EvidenceError(
            "refusing to write invalid proof evidence: " + "; ".join(errors)
        )

    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise EvidenceError(f"evidence output already exists: {path}") from exc
    except OSError as exc:
        raise EvidenceError(f"cannot write evidence output {path}: {exc}") from exc
