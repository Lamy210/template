from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


SCHEMA_VERSION = 1
SCHEMA_FIELDS = {
    "schemaVersion",
    "sourceRepository",
    "sourceRunId",
    "sourceRunAttempt",
    "sourceSHA",
    "tag",
    "sourceArtifactId",
    "sourceArtifactDigest",
    "archiveSha256",
    "publisherRunId",
    "publisherSHA",
    "dmgSha256",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class ExpectedRelease:
    source_repository: str
    source_run_id: int
    source_run_attempt: int
    source_sha: str
    tag: str
    source_artifact_id: int
    source_artifact_digest: str
    archive_sha256: str
    publisher_run_id: int
    publisher_sha: str
    dmg_path: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def validate_release_attestation(document: object) -> list[str]:
    if not isinstance(document, dict):
        return ["release attestation must be a JSON object"]

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

    for field in (
        "sourceRunId",
        "sourceRunAttempt",
        "sourceArtifactId",
        "publisherRunId",
    ):
        value = document.get(field)
        if type(value) is not int or value <= 0:
            errors.append(f"{field} must be a positive integer")

    repository = document.get("sourceRepository")
    repository_valid = (
        isinstance(repository, str)
        and REPOSITORY_RE.fullmatch(repository) is not None
        and all(component not in {".", ".."} for component in repository.split("/", 1))
    )
    if not repository_valid:
        errors.append("sourceRepository must be in owner/repo form")

    for field in ("sourceSHA", "publisherSHA"):
        value = document.get(field)
        if not isinstance(value, str) or SHA_RE.fullmatch(value) is None:
            errors.append(f"{field} must be 40 lowercase hexadecimal characters")

    tag = document.get("tag")
    if not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None:
        errors.append("tag must match stable SemVer form vX.Y.Z")

    for field in (
        "sourceArtifactDigest",
        "archiveSha256",
        "dmgSha256",
    ):
        value = document.get(field)
        if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
            errors.append(f"{field} must use sha256:<64 lowercase hex>")

    return errors


def verify_release_attestation(
    document: object,
    expected: ExpectedRelease,
) -> list[str]:
    errors = validate_release_attestation(document)
    if not isinstance(document, dict):
        return errors

    expected_values = {
        "sourceRepository": expected.source_repository,
        "sourceRunId": expected.source_run_id,
        "sourceRunAttempt": expected.source_run_attempt,
        "sourceSHA": expected.source_sha,
        "tag": expected.tag,
        "sourceArtifactId": expected.source_artifact_id,
        "sourceArtifactDigest": expected.source_artifact_digest,
        "archiveSha256": expected.archive_sha256,
        "publisherRunId": expected.publisher_run_id,
        "publisherSHA": expected.publisher_sha,
    }
    for field, expected_value in expected_values.items():
        if document.get(field) != expected_value:
            errors.append(f"{field} does not match expected release identity")

    if not expected.dmg_path.is_file():
        errors.append(f"release DMG is missing: {expected.dmg_path}")
    else:
        actual_dmg_digest = sha256_file(expected.dmg_path)
        if document.get("dmgSha256") != actual_dmg_digest:
            errors.append(
                "dmgSha256 does not match the exact release DMG: "
                f"{actual_dmg_digest}"
            )

    return errors


def build_release_attestation(expected: ExpectedRelease) -> dict[str, object]:
    if not expected.dmg_path.is_file():
        raise ValueError(f"DMG not found: {expected.dmg_path}")

    document: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "sourceRepository": expected.source_repository,
        "sourceRunId": expected.source_run_id,
        "sourceRunAttempt": expected.source_run_attempt,
        "sourceSHA": expected.source_sha,
        "tag": expected.tag,
        "sourceArtifactId": expected.source_artifact_id,
        "sourceArtifactDigest": expected.source_artifact_digest,
        "archiveSha256": expected.archive_sha256,
        "publisherRunId": expected.publisher_run_id,
        "publisherSHA": expected.publisher_sha,
        "dmgSha256": sha256_file(expected.dmg_path),
    }
    errors = validate_release_attestation(document)
    if errors:
        raise ValueError("; ".join(errors))
    return document
