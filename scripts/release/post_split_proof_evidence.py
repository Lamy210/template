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


def write_evidence(path: Path, evidence: dict[str, object]) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise EvidenceError(f"evidence output already exists: {path}") from exc
    except OSError as exc:
        raise EvidenceError(f"cannot write evidence output {path}: {exc}") from exc
