from __future__ import annotations

import re
from typing import Any


GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVENANCE_FIELDS = {
    "schemaVersion",
    "repository",
    "repositoryId",
    "workflow",
    "runId",
    "runAttempt",
    "sourceSHA",
    "artifactName",
    "coverageProfileFingerprint",
}


class ValidationError(ValueError):
    pass


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{field} must be a positive integer")
    return value


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} must be a non-empty string")
    if value != value.strip() or "\n" in value or "\r" in value:
        raise ValidationError(f"{field} must be one canonical line")
    return value


def validate_coverage_baseline_provenance(
    resolver: Any,
    provenance: Any,
    summary: Any,
    *,
    expected_repository: str,
    expected_workflow: str,
    expected_artifact: str,
) -> dict[str, Any]:
    if not isinstance(resolver, dict):
        raise ValidationError("resolver metadata must be an object")
    if not isinstance(provenance, dict):
        raise ValidationError("coverage baseline provenance must be an object")
    if not isinstance(summary, dict):
        raise ValidationError("coverage baseline summary must be an object")

    if set(provenance) != PROVENANCE_FIELDS:
        missing = sorted(PROVENANCE_FIELDS - set(provenance))
        extra = sorted(set(provenance) - PROVENANCE_FIELDS)
        raise ValidationError(
            f"coverage baseline provenance fields mismatch: missing={missing}, extra={extra}"
        )
    if provenance.get("schemaVersion") != 1:
        raise ValidationError("coverage baseline provenance schemaVersion must equal 1")

    repository = _non_empty_string(resolver.get("repository"), "resolver repository")
    repository_id = _positive_int(resolver.get("repositoryId"), "resolver repository id")
    workflow = _non_empty_string(resolver.get("workflow"), "resolver workflow")
    workflow_id = _positive_int(resolver.get("workflowId"), "resolver workflow id")
    run_id = _positive_int(resolver.get("runId"), "resolver run id")
    run_attempt = _positive_int(resolver.get("runAttempt"), "resolver run attempt")
    source_sha = _non_empty_string(resolver.get("sourceSHA"), "resolver source SHA")
    artifact_id = _positive_int(resolver.get("artifactId"), "resolver artifact id")
    artifact_name = _non_empty_string(resolver.get("artifactName"), "resolver artifact name")
    artifact_digest = _non_empty_string(
        resolver.get("artifactDigest"), "resolver artifact digest"
    )
    event = _non_empty_string(resolver.get("event"), "resolver event")

    if repository != expected_repository:
        raise ValidationError("resolver repository does not match expected repository")
    if workflow != expected_workflow:
        raise ValidationError("resolver workflow does not match expected workflow")
    if artifact_name != expected_artifact:
        raise ValidationError("resolver artifact does not match expected artifact")
    if event != "push":
        raise ValidationError("coverage baseline resolver event must be push")
    if not GIT_SHA_RE.fullmatch(source_sha):
        raise ValidationError("resolver source SHA must be 40 lowercase hex characters")
    if not DIGEST_RE.fullmatch(artifact_digest):
        raise ValidationError("resolver artifact digest must be sha256:<64 lowercase hex>")

    expected_values = {
        "repository": repository,
        "repositoryId": repository_id,
        "workflow": workflow,
        "runId": run_id,
        "runAttempt": run_attempt,
        "sourceSHA": source_sha,
        "artifactName": artifact_name,
    }
    for field, expected in expected_values.items():
        if provenance.get(field) != expected:
            raise ValidationError(
                f"coverage baseline provenance {field} does not match resolver metadata"
            )

    fingerprint = _non_empty_string(
        provenance.get("coverageProfileFingerprint"),
        "coverage baseline profile fingerprint",
    )
    if not DIGEST_RE.fullmatch(fingerprint):
        raise ValidationError(
            "coverage baseline profile fingerprint must be sha256:<64 lowercase hex>"
        )
    if summary.get("schemaVersion") != 1:
        raise ValidationError("coverage baseline summary schemaVersion must equal 1")
    if summary.get("coverageProfileFingerprint") != fingerprint:
        raise ValidationError(
            "coverage baseline summary profile fingerprint does not match provenance"
        )

    return {
        "repository": repository,
        "repositoryId": repository_id,
        "workflow": workflow,
        "workflowId": workflow_id,
        "runId": run_id,
        "runAttempt": run_attempt,
        "sourceSHA": source_sha,
        "artifactId": artifact_id,
        "artifactName": artifact_name,
        "artifactDigest": artifact_digest,
        "coverageProfileFingerprint": fingerprint,
    }
