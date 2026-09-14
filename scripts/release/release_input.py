from __future__ import annotations

import hashlib
import os
from pathlib import Path
import plistlib
import re
import subprocess
import tempfile

from scripts.release.release_provenance import ExpectedBuild, validate_build_provenance


SOURCE_METADATA_FIELDS = {
    "schemaVersion",
    "repository",
    "workflowId",
    "workflowPath",
    "runId",
    "runAttempt",
    "sourceSHA",
    "artifactId",
    "artifactName",
    "artifactDigest",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return f"sha256:{hasher.hexdigest()}"


def _validate_source_metadata(
    metadata: object,
    *,
    expected_repository: str,
    expected_workflow_path: str,
) -> list[str]:
    if not isinstance(metadata, dict):
        return ["source metadata must be a JSON object"]

    errors: list[str] = []
    fields = set(metadata)
    missing = sorted(SOURCE_METADATA_FIELDS - fields)
    unexpected = sorted(fields - SOURCE_METADATA_FIELDS)
    if missing:
        errors.append(f"source metadata missing fields: {missing!r}")
    if unexpected:
        errors.append(f"source metadata has unexpected fields: {unexpected!r}")

    schema_version = metadata.get("schemaVersion")
    if type(schema_version) is not int or schema_version != 1:
        errors.append("source metadata schemaVersion must equal integer 1")

    if metadata.get("repository") != expected_repository:
        errors.append("source metadata repository does not match expected repository")
    if metadata.get("workflowPath") != expected_workflow_path:
        errors.append("source metadata workflowPath does not match expected workflow path")

    for field in ("workflowId", "runId", "runAttempt", "artifactId"):
        value = metadata.get(field)
        if type(value) is not int or value <= 0:
            errors.append(f"source metadata {field} must be a positive integer")

    source_sha = metadata.get("sourceSHA")
    if not isinstance(source_sha, str) or SHA_RE.fullmatch(source_sha) is None:
        errors.append("source metadata sourceSHA must be 40 lowercase hexadecimal characters")

    digest = metadata.get("artifactDigest")
    if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
        errors.append("source metadata artifactDigest must use sha256:<64 lowercase hex>")

    run_id = metadata.get("runId")
    run_attempt = metadata.get("runAttempt")
    if type(run_id) is int and run_id > 0 and type(run_attempt) is int and run_attempt > 0:
        expected_artifact_name = f"unsigned-macos-release-{run_id}-{run_attempt}"
        if metadata.get("artifactName") != expected_artifact_name:
            errors.append(f"source metadata artifactName must equal {expected_artifact_name}")
    elif not isinstance(metadata.get("artifactName"), str):
        errors.append("source metadata artifactName must be a string")

    return errors


def _safe_executable_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


def validate_release_input(
    *,
    provenance_document: object,
    source_metadata: object,
    archive_path: Path,
    expected_repository: str,
    expected_workflow_path: str,
    expected_app_basename: str,
    expected_bundle_id: str,
    resolved_tag_sha: str,
    source_is_ancestor: bool,
    publisher_sha: str,
    release_scripts_root: Path,
) -> tuple[list[str], dict[str, object] | None]:
    errors = _validate_source_metadata(
        source_metadata,
        expected_repository=expected_repository,
        expected_workflow_path=expected_workflow_path,
    )

    if not isinstance(publisher_sha, str) or SHA_RE.fullmatch(publisher_sha) is None:
        errors.append("publisher SHA must be 40 lowercase hexadecimal characters")
    if not isinstance(resolved_tag_sha, str) or SHA_RE.fullmatch(resolved_tag_sha) is None:
        errors.append("resolved tag SHA must be 40 lowercase hexadecimal characters")
    if source_is_ancestor is not True:
        errors.append("source commit is not reachable from the current default branch")

    if not archive_path.is_file():
        errors.append(f"release archive is missing: {archive_path}")
        return errors, None

    metadata = source_metadata if isinstance(source_metadata, dict) else {}
    source_sha = metadata.get("sourceSHA")
    if isinstance(source_sha, str) and isinstance(resolved_tag_sha, str):
        if resolved_tag_sha != source_sha:
            errors.append("resolved tag SHA does not match source SHA")

    tag = provenance_document.get("tag") if isinstance(provenance_document, dict) else None
    version = tag[1:] if isinstance(tag, str) and TAG_RE.fullmatch(tag) else ""
    run_id = metadata.get("runId")
    run_attempt = metadata.get("runAttempt")
    artifact_name = metadata.get("artifactName")

    if (
        isinstance(tag, str)
        and TAG_RE.fullmatch(tag)
        and type(run_id) is int
        and run_id > 0
        and type(run_attempt) is int
        and run_attempt > 0
        and isinstance(artifact_name, str)
        and isinstance(source_sha, str)
    ):
        expected_build = ExpectedBuild(
            repository=expected_repository,
            workflow_name="Release Build",
            workflow_path=expected_workflow_path,
            run_id=run_id,
            run_attempt=run_attempt,
            source_event="push",
            source_sha=source_sha,
            source_ref=f"refs/tags/{tag}",
            tag=tag,
            artifact_name=artifact_name,
            archive_name="unsigned-macos-app.tar.gz",
            app_basename=expected_app_basename,
            bundle_id=expected_bundle_id,
            version=version,
        )
        errors.extend(validate_build_provenance(provenance_document, expected_build))
    else:
        errors.append("build provenance cannot be bound to validated source metadata")

    actual_archive_digest = _sha256_file(archive_path)
    if not isinstance(provenance_document, dict) or provenance_document.get("archiveSha256") != actual_archive_digest:
        errors.append("archive SHA-256 does not match build provenance")

    if errors:
        return errors, None

    extract_script = release_scripts_root / "extract-app-artifact.sh"
    verify_script = release_scripts_root / "verify-app-executable.sh"
    if not extract_script.is_file() or not verify_script.is_file():
        return ["trusted release validation scripts are missing"], None

    with tempfile.TemporaryDirectory(prefix="validated-release-input.") as temporary_directory:
        extract_root = Path(temporary_directory) / "extracted"
        extract_environment = os.environ.copy()
        extract_environment.update(
            {
                "ARCHIVE_PATH": str(archive_path),
                "OUTPUT_DIR": str(extract_root),
                "APP_BASENAME": expected_app_basename,
            }
        )
        extraction = subprocess.run(
            ["bash", str(extract_script)],
            env=extract_environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if extraction.returncode != 0:
            diagnostic = extraction.stderr.strip() or extraction.stdout.strip() or "unknown error"
            return [f"archive preflight failed: {diagnostic}"], None

        app_path = extract_root / expected_app_basename
        plist_path = app_path / "Contents/Info.plist"
        if not plist_path.is_file() or plist_path.is_symlink():
            return ["application Info.plist is missing or unsafe"], None

        try:
            with plist_path.open("rb") as handle:
                plist = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException) as error:
            return [f"application Info.plist is invalid: {error}"], None
        if not isinstance(plist, dict):
            return ["application Info.plist root must be a dictionary"], None

        bundle_identifier = plist.get("CFBundleIdentifier")
        bundle_version = plist.get("CFBundleShortVersionString")
        executable_name = plist.get("CFBundleExecutable")
        if bundle_identifier != expected_bundle_id:
            return [
                f"bundle identifier mismatch: expected {expected_bundle_id}, got {bundle_identifier}"
            ], None
        if bundle_version != version:
            return [f"bundle version mismatch: expected {version}, got {bundle_version}"], None
        if not _safe_executable_name(executable_name):
            return ["CFBundleExecutable must be a non-empty basename"], None

        verify_environment = os.environ.copy()
        verify_environment.update(
            {
                "APP_PATH": str(app_path),
                "EXECUTABLE_NAME": executable_name,
            }
        )
        verification = subprocess.run(
            ["bash", str(verify_script)],
            env=verify_environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if verification.returncode != 0:
            diagnostic = verification.stderr.strip() or verification.stdout.strip() or "unknown error"
            return [f"bundle executable contract failed: {diagnostic}"], None

    assert isinstance(source_metadata, dict)
    assert isinstance(tag, str)
    validated: dict[str, object] = {
        "schemaVersion": 1,
        "sourceRepository": expected_repository,
        "sourceRunId": source_metadata["runId"],
        "sourceRunAttempt": source_metadata["runAttempt"],
        "sourceSHA": source_metadata["sourceSHA"],
        "tag": tag,
        "sourceArtifactId": source_metadata["artifactId"],
        "sourceArtifactDigest": source_metadata["artifactDigest"],
        "archiveSha256": actual_archive_digest,
        "publisherSHA": publisher_sha,
        "appBasename": expected_app_basename,
        "bundleId": expected_bundle_id,
        "version": version,
    }
    return [], validated
