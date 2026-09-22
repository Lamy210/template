from __future__ import annotations

from dataclasses import dataclass
import re


SCHEMA_VERSION = 1
SCHEMA_FIELDS = {
    "schemaVersion",
    "repository",
    "sourceWorkflowName",
    "sourceWorkflowPath",
    "sourceRunId",
    "sourceRunAttempt",
    "sourceEvent",
    "sourceSHA",
    "sourceRef",
    "tag",
    "artifactName",
    "archiveName",
    "archiveSha256",
    "appBasename",
    "bundleId",
    "version",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW_PATH_RE = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$")


@dataclass(frozen=True)
class ExpectedBuild:
    repository: str
    workflow_name: str
    workflow_path: str
    run_id: int
    run_attempt: int
    source_event: str
    source_sha: str
    source_ref: str
    tag: str
    artifact_name: str
    archive_name: str
    app_basename: str
    bundle_id: str
    version: str


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_safe_basename(value: object, suffix: str) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and value.endswith(suffix)
    )


def validate_build_provenance(document: object, expected: ExpectedBuild) -> list[str]:
    if not isinstance(document, dict):
        return ["build provenance must be a JSON object"]

    errors: list[str] = []
    keys = set(document)
    missing = sorted(SCHEMA_FIELDS - keys)
    unexpected = sorted(keys - SCHEMA_FIELDS)
    if missing:
        errors.append(f"missing fields: {missing!r}")
    if unexpected:
        errors.append(f"unexpected fields: {unexpected!r}")

    schema_version = document.get("schemaVersion")
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        errors.append("schemaVersion must equal integer 1")

    run_id = document.get("sourceRunId")
    if type(run_id) is not int or run_id <= 0:
        errors.append("sourceRunId must be a positive integer")

    run_attempt = document.get("sourceRunAttempt")
    if type(run_attempt) is not int or run_attempt <= 0:
        errors.append("sourceRunAttempt must be a positive integer")

    source_sha = document.get("sourceSHA")
    if not isinstance(source_sha, str) or SHA_RE.fullmatch(source_sha) is None:
        errors.append("sourceSHA must be 40 lowercase hexadecimal characters")

    archive_digest = document.get("archiveSha256")
    if not isinstance(archive_digest, str) or DIGEST_RE.fullmatch(archive_digest) is None:
        errors.append("archiveSha256 must use sha256:<64 lowercase hex>")

    tag = document.get("tag")
    tag_valid = isinstance(tag, str) and TAG_RE.fullmatch(tag) is not None
    if not tag_valid:
        errors.append("tag must match stable SemVer form vX.Y.Z")

    source_ref = document.get("sourceRef")
    version = document.get("version")
    if tag_valid:
        expected_ref = f"refs/tags/{tag}"
        expected_version = tag[1:]
        if source_ref != expected_ref or version != expected_version:
            errors.append("tag/ref/version fields are inconsistent")
    else:
        if not _non_empty_string(source_ref):
            errors.append("sourceRef must be a non-empty string")
        if not _non_empty_string(version):
            errors.append("version must be a non-empty string")

    repository = document.get("repository")
    if not isinstance(repository, str) or REPOSITORY_RE.fullmatch(repository) is None:
        errors.append("repository must be in owner/repo form")

    workflow_path = document.get("sourceWorkflowPath")
    if not isinstance(workflow_path, str) or WORKFLOW_PATH_RE.fullmatch(workflow_path) is None:
        errors.append("sourceWorkflowPath must be a canonical .github/workflows/*.yml path")

    if not _non_empty_string(document.get("sourceWorkflowName")):
        errors.append("sourceWorkflowName must be a non-empty string")
    if document.get("sourceEvent") != "push":
        errors.append("sourceEvent must equal push")

    artifact_name = document.get("artifactName")
    if type(run_id) is int and run_id > 0 and type(run_attempt) is int and run_attempt > 0:
        canonical_artifact_name = f"unsigned-macos-release-{run_id}-{run_attempt}"
        if artifact_name != canonical_artifact_name:
            errors.append(f"artifactName must equal {canonical_artifact_name}")
    elif not _non_empty_string(artifact_name):
        errors.append("artifactName must be a non-empty string")

    if not _is_safe_basename(document.get("archiveName"), ".tar.gz"):
        errors.append("archiveName must be a safe .tar.gz basename")
    if not _is_safe_basename(document.get("appBasename"), ".app"):
        errors.append("appBasename must be a safe .app basename")
    if not _non_empty_string(document.get("bundleId")):
        errors.append("bundleId must be a non-empty string")

    expected_values = {
        "repository": expected.repository,
        "sourceWorkflowName": expected.workflow_name,
        "sourceWorkflowPath": expected.workflow_path,
        "sourceRunId": expected.run_id,
        "sourceRunAttempt": expected.run_attempt,
        "sourceEvent": expected.source_event,
        "sourceSHA": expected.source_sha,
        "sourceRef": expected.source_ref,
        "tag": expected.tag,
        "artifactName": expected.artifact_name,
        "archiveName": expected.archive_name,
        "appBasename": expected.app_basename,
        "bundleId": expected.bundle_id,
        "version": expected.version,
    }
    for field, expected_value in expected_values.items():
        if document.get(field) != expected_value:
            errors.append(f"{field} does not match independently expected value")

    return errors


def build_provenance(expected: ExpectedBuild, archive_sha256: str) -> dict[str, object]:
    document: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "repository": expected.repository,
        "sourceWorkflowName": expected.workflow_name,
        "sourceWorkflowPath": expected.workflow_path,
        "sourceRunId": expected.run_id,
        "sourceRunAttempt": expected.run_attempt,
        "sourceEvent": expected.source_event,
        "sourceSHA": expected.source_sha,
        "sourceRef": expected.source_ref,
        "tag": expected.tag,
        "artifactName": expected.artifact_name,
        "archiveName": expected.archive_name,
        "archiveSha256": archive_sha256,
        "appBasename": expected.app_basename,
        "bundleId": expected.bundle_id,
        "version": expected.version,
    }
    errors = validate_build_provenance(document, expected)
    if errors:
        raise ValueError("; ".join(errors))
    return document
