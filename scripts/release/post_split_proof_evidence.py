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
PUBLISHER_FIELDS_V2 = {
    "runAttempt",
    "runId",
    "sha",
    "validatorArtifactDigest",
    "validatorArtifactId",
    "workflowName",
    "workflowPath",
}
PUBLISHER_FIELDS_V3 = PUBLISHER_FIELDS_V2 | {"validationJob"}
VALIDATION_JOB_FIELDS = {
    "conclusion",
    "headBranch",
    "headSHA",
    "id",
    "name",
    "runAttempt",
    "runId",
    "status",
    "workflowName",
}
REPOSITORY_FIELDS = {"defaultBranch", "fullName", "id"}
SOURCE_FIELDS_V2_V3 = {
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
SOURCE_FIELDS_V4 = SOURCE_FIELDS_V2_V3 | {"liveTag"}
LIVE_TAG_FIELDS = {"annotatedChain", "ref", "refTarget", "resolvedSHA"}
GIT_TARGET_FIELDS = {"sha", "type"}
ANNOTATED_TAG_FIELDS = {"sha", "tag", "target"}

SOURCE_WORKFLOW_NAME = "Release Build"
SOURCE_WORKFLOW_PATH = ".github/workflows/release-build.yml"
PUBLISHER_WORKFLOW_NAME = "Release Publisher"
PUBLISHER_WORKFLOW_PATH = ".github/workflows/release-publisher.yml"
PUBLISHER_VALIDATION_JOB_NAME = "Validate release input without secrets"


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


def _source_artifact(
    artifacts: object,
    *,
    source_run_id: int,
    source_run_attempt: int,
) -> dict[str, Any]:
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
        raise EvidenceError("source artifacts must be an array of objects")

    expected_name = f"unsigned-macos-release-{source_run_id}-{source_run_attempt}"
    matches = [item for item in artifacts if item.get("name") == expected_name]
    if len(matches) != 1:
        raise EvidenceError(
            f"expected exactly one source artifact named {expected_name!r}"
        )
    return matches[0]


def _git_target(value: object, label: str) -> dict[str, str]:
    target = _object(value, label)
    target_type = target.get("type")
    if target_type not in {"commit", "tag"}:
        raise EvidenceError(f"{label} type must be 'commit' or 'tag'")
    target_sha = _sha(target.get("sha"), f"{label} SHA")
    return {"sha": target_sha, "type": target_type}


def _live_tag_binding(
    tag_ref: object,
    tag_objects: object,
    *,
    source_tag: str,
    source_sha: str,
) -> dict[str, object]:
    ref = _object(tag_ref, "live release tag ref")
    expected_ref = f"refs/tags/{source_tag}"
    if ref.get("ref") != expected_ref:
        raise EvidenceError("live release tag ref does not match source tag")

    ref_target = _git_target(ref.get("object"), "live release tag target")
    if not isinstance(tag_objects, list) or any(
        not isinstance(item, dict) for item in tag_objects
    ):
        raise EvidenceError("annotated release tag objects must be an array of objects")

    objects_by_sha: dict[str, dict[str, Any]] = {}
    for index, document in enumerate(tag_objects):
        document_sha = _sha(
            document.get("sha"), f"annotated release tag object {index} SHA"
        )
        if document_sha in objects_by_sha:
            raise EvidenceError(
                f"duplicate annotated release tag object SHA: {document_sha}"
            )
        objects_by_sha[document_sha] = document

    current = ref_target
    chain: list[dict[str, object]] = []
    seen: set[str] = set()

    for depth in range(8):
        if current["type"] == "commit":
            if current["sha"] != source_sha:
                raise EvidenceError(
                    "live release tag resolves to a different SHA than source SHA"
                )
            if set(objects_by_sha) != seen:
                unexpected = sorted(set(objects_by_sha) - seen)
                raise EvidenceError(
                    "unexpected annotated release tag objects were collected: "
                    f"{unexpected!r}"
                )
            return {
                "annotatedChain": chain,
                "ref": expected_ref,
                "refTarget": ref_target,
                "resolvedSHA": source_sha,
            }

        current_sha = current["sha"]
        if current_sha in seen:
            raise EvidenceError(
                f"annotated release tag chain contains a cycle at {current_sha}"
            )
        seen.add(current_sha)

        document = objects_by_sha.get(current_sha)
        if document is None:
            raise EvidenceError(
                f"annotated release tag object is missing for target SHA {current_sha}"
            )

        tag_name = _string(
            document.get("tag"),
            f"annotated release tag object {current_sha} tag",
        )
        if "\n" in tag_name or "\r" in tag_name:
            raise EvidenceError("annotated release tag object tag must be single-line")
        if depth == 0 and tag_name != source_tag:
            raise EvidenceError(
                "outer annotated release tag object name does not match source tag"
            )

        target = _git_target(
            document.get("object"),
            f"annotated release tag object {current_sha} target",
        )
        chain.append(
            {
                "sha": current_sha,
                "tag": tag_name,
                "target": target,
            }
        )
        current = target

    raise EvidenceError("live release tag exceeded maximum annotated-tag dereference depth")


def _publisher_validation_job(
    jobs: object,
    *,
    publisher_run_id: int,
    publisher_run_attempt: int,
    publisher_sha: str,
    default_branch: str,
) -> dict[str, object]:
    if not isinstance(jobs, list) or any(not isinstance(item, dict) for item in jobs):
        raise EvidenceError("publisher jobs must be an array of objects")

    matches = [
        item for item in jobs if item.get("name") == PUBLISHER_VALIDATION_JOB_NAME
    ]
    if len(matches) != 1:
        raise EvidenceError(
            "expected exactly one publisher validation job named "
            f"{PUBLISHER_VALIDATION_JOB_NAME!r}"
        )

    job = matches[0]
    job_id = _positive_int(job.get("id"), "publisher validation job id")
    if job.get("run_id") != publisher_run_id:
        raise EvidenceError("publisher validation job run_id does not match publisher run")
    if job.get("head_sha") != publisher_sha:
        raise EvidenceError("publisher validation job head_sha does not match publisher SHA")
    if job.get("workflow_name") != PUBLISHER_WORKFLOW_NAME:
        raise EvidenceError(
            "publisher validation job workflow_name does not match publisher workflow"
        )
    if job.get("head_branch") != default_branch:
        raise EvidenceError(
            "publisher validation job head_branch does not match default branch"
        )
    if job.get("status") != "completed":
        raise EvidenceError("publisher validation job must be completed")
    if job.get("conclusion") != "success":
        raise EvidenceError("publisher validation job must conclude successfully")

    return {
        "conclusion": "success",
        "headBranch": default_branch,
        "headSHA": publisher_sha,
        "id": job_id,
        "name": PUBLISHER_VALIDATION_JOB_NAME,
        "runAttempt": publisher_run_attempt,
        "runId": publisher_run_id,
        "status": "completed",
        "workflowName": PUBLISHER_WORKFLOW_NAME,
    }


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
    publisher_jobs: object,
    tag_ref: object,
    tag_objects: object,
    source_artifacts: object,
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

    live_tag = _live_tag_binding(
        tag_ref,
        tag_objects,
        source_tag=source_tag,
        source_sha=source_sha,
    )

    publisher_run_id = _positive_int(publisher.get("id"), "publisher run id")
    publisher_run_attempt = _positive_int(
        publisher.get("run_attempt"), "publisher run attempt"
    )
    publisher_sha = _sha(publisher.get("head_sha"), "publisher SHA")

    validation_job = _publisher_validation_job(
        publisher_jobs,
        publisher_run_id=publisher_run_id,
        publisher_run_attempt=publisher_run_attempt,
        publisher_sha=publisher_sha,
        default_branch=default_branch,
    )

    initial_head_sha = _sha(initial_head.get("sha"), "initial default-head SHA")
    final_head_sha = _sha(final_head.get("sha"), "final default-head SHA")
    if initial_head_sha != publisher_sha or final_head_sha != publisher_sha:
        raise EvidenceError("default-head snapshots must equal publisher SHA")

    source_artifact = _source_artifact(
        source_artifacts,
        source_run_id=source_run_id,
        source_run_attempt=source_run_attempt,
    )
    source_artifact_id = _positive_int(source_artifact.get("id"), "source artifact id")
    source_artifact_digest = _digest(
        source_artifact.get("digest"), "source artifact digest"
    )
    if validated_metadata.get("sourceArtifactId") != source_artifact_id:
        raise EvidenceError("validator metadata sourceArtifactId does not match source artifact")
    if validated_metadata.get("sourceArtifactDigest") != source_artifact_digest:
        raise EvidenceError(
            "validator metadata sourceArtifactDigest does not match source artifact"
        )

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
            "validationJob": validation_job,
            "workflowName": _string(publisher.get("name"), "publisher workflow name"),
            "workflowPath": _string(publisher.get("path"), "publisher workflow path"),
        },
        "repository": {
            "defaultBranch": default_branch,
            "fullName": repository_full_name,
            "id": repository_id,
        },
        "schemaVersion": 4,
        "source": {
            "archiveDigest": unsigned_archive_digest,
            "artifactDigest": source_artifact_digest,
            "artifactId": source_artifact_id,
            "liveTag": live_tag,
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
    if type(schema_version) is not int or schema_version not in {2, 3, 4}:
        errors.append("schemaVersion must equal integer 2, 3, or 4")
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

    source_fields = SOURCE_FIELDS_V4 if schema_version == 4 else SOURCE_FIELDS_V2_V3
    source_errors, source = _closed_object_errors(
        root.get("source"),
        label="source",
        expected_fields=source_fields,
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

        if schema_version == 4:
            live_tag_errors, live_tag = _closed_object_errors(
                source.get("liveTag"),
                label="source.liveTag",
                expected_fields=LIVE_TAG_FIELDS,
            )
            errors.extend(live_tag_errors)
            if live_tag is not None:
                expected_ref = (
                    f"refs/tags/{source_tag}"
                    if isinstance(source_tag, str)
                    and TAG_RE.fullmatch(source_tag) is not None
                    else None
                )
                if expected_ref is not None and live_tag.get("ref") != expected_ref:
                    errors.append("source.liveTag.ref must match source.tag")

                ref_target_errors, ref_target = _closed_object_errors(
                    live_tag.get("refTarget"),
                    label="source.liveTag.refTarget",
                    expected_fields=GIT_TARGET_FIELDS,
                )
                errors.extend(ref_target_errors)

                resolved_sha = live_tag.get("resolvedSHA")
                if (
                    not isinstance(resolved_sha, str)
                    or SHA_RE.fullmatch(resolved_sha) is None
                ):
                    errors.append(
                        "source.liveTag.resolvedSHA must be 40 lowercase hexadecimal characters"
                    )

                chain = live_tag.get("annotatedChain")
                if not isinstance(chain, list):
                    errors.append("source.liveTag.annotatedChain must be an array")
                    chain = []
                elif len(chain) > 8:
                    errors.append(
                        "source.liveTag.annotatedChain must contain at most 8 objects"
                    )

                current_target = ref_target
                seen_chain_shas: set[str] = set()
                for index, item in enumerate(chain):
                    item_errors, tag_object = _closed_object_errors(
                        item,
                        label=f"source.liveTag.annotatedChain[{index}]",
                        expected_fields=ANNOTATED_TAG_FIELDS,
                    )
                    errors.extend(item_errors)
                    if tag_object is None:
                        current_target = None
                        continue

                    tag_object_sha = tag_object.get("sha")
                    if (
                        not isinstance(tag_object_sha, str)
                        or SHA_RE.fullmatch(tag_object_sha) is None
                    ):
                        errors.append(
                            f"source.liveTag.annotatedChain[{index}].sha must be 40 lowercase hexadecimal characters"
                        )
                    elif tag_object_sha in seen_chain_shas:
                        errors.append(
                            "source.liveTag.annotatedChain must not repeat tag object SHAs"
                        )
                    else:
                        seen_chain_shas.add(tag_object_sha)

                    tag_name = tag_object.get("tag")
                    if (
                        not isinstance(tag_name, str)
                        or not tag_name
                        or "\n" in tag_name
                        or "\r" in tag_name
                    ):
                        errors.append(
                            f"source.liveTag.annotatedChain[{index}].tag must be a non-empty single-line string"
                        )
                    elif index == 0 and isinstance(source_tag, str) and tag_name != source_tag:
                        errors.append(
                            "source.liveTag outer annotated tag name must equal source.tag"
                        )

                    target_errors, next_target = _closed_object_errors(
                        tag_object.get("target"),
                        label=f"source.liveTag.annotatedChain[{index}].target",
                        expected_fields=GIT_TARGET_FIELDS,
                    )
                    errors.extend(target_errors)
                    if next_target is not None:
                        target_type = next_target.get("type")
                        target_sha = next_target.get("sha")
                        if target_type not in {"commit", "tag"}:
                            errors.append(
                                f"source.liveTag.annotatedChain[{index}].target.type must be 'commit' or 'tag'"
                            )
                        if (
                            not isinstance(target_sha, str)
                            or SHA_RE.fullmatch(target_sha) is None
                        ):
                            errors.append(
                                f"source.liveTag.annotatedChain[{index}].target.sha must be 40 lowercase hexadecimal characters"
                            )

                    if current_target is not None:
                        if current_target.get("type") != "tag":
                            errors.append(
                                "source.liveTag annotated chain must be empty after a commit target"
                            )
                        elif (
                            isinstance(tag_object_sha, str)
                            and SHA_RE.fullmatch(tag_object_sha) is not None
                            and current_target.get("sha") != tag_object_sha
                        ):
                            errors.append(
                                "source.liveTag annotated chain does not follow ref/tag targets"
                            )
                    current_target = next_target

                if ref_target is not None:
                    ref_type = ref_target.get("type")
                    ref_sha = ref_target.get("sha")
                    if ref_type not in {"commit", "tag"}:
                        errors.append(
                            "source.liveTag.refTarget.type must be 'commit' or 'tag'"
                        )
                    if not isinstance(ref_sha, str) or SHA_RE.fullmatch(ref_sha) is None:
                        errors.append(
                            "source.liveTag.refTarget.sha must be 40 lowercase hexadecimal characters"
                        )

                if current_target is not None:
                    if current_target.get("type") != "commit":
                        errors.append(
                            "source.liveTag annotated chain must resolve to a commit"
                        )
                    elif (
                        isinstance(resolved_sha, str)
                        and SHA_RE.fullmatch(resolved_sha) is not None
                        and current_target.get("sha") != resolved_sha
                    ):
                        errors.append(
                            "source.liveTag final target must equal source.liveTag.resolvedSHA"
                        )

                if (
                    isinstance(source_sha, str)
                    and SHA_RE.fullmatch(source_sha) is not None
                    and isinstance(resolved_sha, str)
                    and SHA_RE.fullmatch(resolved_sha) is not None
                    and resolved_sha != source_sha
                ):
                    errors.append(
                        "source.liveTag.resolvedSHA must equal source.sha"
                    )

    publisher_fields = (
        PUBLISHER_FIELDS_V3 if schema_version in {3, 4} else PUBLISHER_FIELDS_V2
    )
    publisher_errors, publisher = _closed_object_errors(
        root.get("publisher"),
        label="publisher",
        expected_fields=publisher_fields,
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

        if schema_version in {3, 4}:
            validation_job_errors, validation_job = _closed_object_errors(
                publisher.get("validationJob"),
                label="publisher.validationJob",
                expected_fields=VALIDATION_JOB_FIELDS,
            )
            errors.extend(validation_job_errors)
            if validation_job is not None:
                for field in ("id", "runId", "runAttempt"):
                    if not _is_positive_int(validation_job.get(field)):
                        errors.append(
                            f"publisher.validationJob.{field} must be a positive integer"
                        )
                head_sha = validation_job.get("headSHA")
                if not isinstance(head_sha, str) or SHA_RE.fullmatch(head_sha) is None:
                    errors.append(
                        "publisher.validationJob.headSHA must be 40 lowercase hexadecimal characters"
                    )
                if validation_job.get("name") != PUBLISHER_VALIDATION_JOB_NAME:
                    errors.append(
                        "publisher.validationJob.name must equal "
                        f"{PUBLISHER_VALIDATION_JOB_NAME!r}"
                    )
                if validation_job.get("workflowName") != PUBLISHER_WORKFLOW_NAME:
                    errors.append(
                        "publisher.validationJob.workflowName must equal "
                        f"{PUBLISHER_WORKFLOW_NAME!r}"
                    )
                head_branch = validation_job.get("headBranch")
                if (
                    not isinstance(head_branch, str)
                    or not head_branch
                    or "\n" in head_branch
                    or "\r" in head_branch
                ):
                    errors.append(
                        "publisher.validationJob.headBranch must be a non-empty single-line string"
                    )
                if validation_job.get("status") != "completed":
                    errors.append(
                        "publisher.validationJob.status must equal 'completed'"
                    )
                if validation_job.get("conclusion") != "success":
                    errors.append(
                        "publisher.validationJob.conclusion must equal 'success'"
                    )

    if schema_version in {3, 4} and publisher is not None and repository is not None:
        validation_job = publisher.get("validationJob")
        if isinstance(validation_job, dict):
            if (
                _is_positive_int(validation_job.get("runId"))
                and _is_positive_int(publisher.get("runId"))
                and validation_job.get("runId") != publisher.get("runId")
            ):
                errors.append(
                    "publisher.validationJob.runId must equal publisher.runId"
                )
            if (
                _is_positive_int(validation_job.get("runAttempt"))
                and _is_positive_int(publisher.get("runAttempt"))
                and validation_job.get("runAttempt") != publisher.get("runAttempt")
            ):
                errors.append(
                    "publisher.validationJob.runAttempt must equal publisher.runAttempt"
                )
            validation_sha = validation_job.get("headSHA")
            publisher_sha = publisher.get("sha")
            if (
                isinstance(validation_sha, str)
                and SHA_RE.fullmatch(validation_sha) is not None
                and isinstance(publisher_sha, str)
                and SHA_RE.fullmatch(publisher_sha) is not None
                and validation_sha != publisher_sha
            ):
                errors.append(
                    "publisher.validationJob.headSHA must equal publisher.sha"
                )
            default_branch = repository.get("defaultBranch")
            head_branch = validation_job.get("headBranch")
            if (
                isinstance(default_branch, str)
                and default_branch
                and isinstance(head_branch, str)
                and head_branch
                and head_branch != default_branch
            ):
                errors.append(
                    "publisher.validationJob.headBranch must equal repository.defaultBranch"
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
