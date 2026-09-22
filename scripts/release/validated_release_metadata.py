from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re


METADATA_FIELDS = {
    "schemaVersion",
    "sourceRepository",
    "sourceRunId",
    "sourceRunAttempt",
    "sourceSHA",
    "tag",
    "sourceArtifactId",
    "sourceArtifactDigest",
    "archiveSha256",
    "publisherSHA",
    "publisherRunId",
    "publisherRunAttempt",
    "validatedAt",
    "appBasename",
    "bundleId",
    "version",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


@dataclass(frozen=True)
class ExpectedValidatedRelease:
    source_repository: str
    source_run_id: int
    source_run_attempt: int
    source_artifact_id: int
    source_artifact_digest: str
    source_sha: str
    source_tag: str
    source_version: str
    publisher_sha: str
    publisher_run_id: int
    publisher_run_attempt: int
    archive_sha256: str
    app_basename: str
    bundle_id: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _valid_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def _safe_app_basename(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and value.endswith(".app")
    )


def verify_validated_release_metadata(
    document: object,
    archive_path: Path,
    expected: ExpectedValidatedRelease,
) -> list[str]:
    if not isinstance(document, dict):
        return ["validated release metadata must be a JSON object"]

    errors: list[str] = []
    fields = set(document)
    missing = sorted(METADATA_FIELDS - fields)
    unexpected = sorted(fields - METADATA_FIELDS)
    if missing:
        errors.append(f"missing fields: {missing!r}")
    if unexpected:
        errors.append(f"unexpected fields: {unexpected!r}")

    schema_version = document.get("schemaVersion")
    if type(schema_version) is not int or schema_version != 1:
        errors.append("schemaVersion must equal integer 1")

    for field in (
        "sourceRunId",
        "sourceRunAttempt",
        "sourceArtifactId",
        "publisherRunId",
        "publisherRunAttempt",
    ):
        value = document.get(field)
        if type(value) is not int or value <= 0:
            errors.append(f"{field} must be a positive integer")

    for field in ("sourceSHA", "publisherSHA"):
        value = document.get(field)
        if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
            errors.append(f"{field} must be 40 lowercase hexadecimal characters")

    for field in ("sourceArtifactDigest", "archiveSha256"):
        value = document.get(field)
        if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
            errors.append(f"{field} must use sha256:<64 lowercase hex>")

    if not _valid_utc_timestamp(document.get("validatedAt")):
        errors.append("validatedAt must be canonical UTC RFC3339 seconds (YYYY-MM-DDTHH:MM:SSZ)")

    tag = document.get("tag")
    version = document.get("version")
    if not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None:
        errors.append("tag must match stable SemVer form vX.Y.Z")
    elif version != tag[1:]:
        errors.append("tag/version fields are inconsistent")

    if not _safe_app_basename(document.get("appBasename")):
        errors.append("appBasename must be a safe .app basename")
    bundle_id = document.get("bundleId")
    if not isinstance(bundle_id, str) or not bundle_id:
        errors.append("bundleId must be a non-empty string")
    source_repository = document.get("sourceRepository")
    if not isinstance(source_repository, str) or "/" not in source_repository:
        errors.append("sourceRepository must be in owner/repo form")

    expected_values = {
        "sourceRepository": expected.source_repository,
        "sourceRunId": expected.source_run_id,
        "sourceRunAttempt": expected.source_run_attempt,
        "sourceArtifactId": expected.source_artifact_id,
        "sourceArtifactDigest": expected.source_artifact_digest,
        "sourceSHA": expected.source_sha,
        "tag": expected.source_tag,
        "version": expected.source_version,
        "publisherSHA": expected.publisher_sha,
        "publisherRunId": expected.publisher_run_id,
        "publisherRunAttempt": expected.publisher_run_attempt,
        "archiveSha256": expected.archive_sha256,
        "appBasename": expected.app_basename,
        "bundleId": expected.bundle_id,
    }
    for field, expected_value in expected_values.items():
        if document.get(field) != expected_value:
            errors.append(f"{field} does not match expected validated release input")

    if not archive_path.is_file():
        errors.append(f"validated release archive is missing: {archive_path}")
    else:
        actual_digest = _sha256_file(archive_path)
        if actual_digest != expected.archive_sha256:
            errors.append(
                f"actual archive SHA-256 does not match expected digest: {actual_digest}"
            )
        if document.get("archiveSha256") != actual_digest:
            errors.append("actual archive SHA-256 does not match validated metadata")

    return errors
