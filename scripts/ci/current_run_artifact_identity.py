#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ValidationError(ValueError):
    pass


def positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{field} must be a positive integer")
    return value


def canonical_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} must be a non-empty string")
    if value != value.strip() or "\n" in value or "\r" in value:
        raise ValidationError(f"{field} must be one canonical line")
    return value


def validate_current_run_artifact(
    metadata: Any,
    *,
    expected_artifact_id: int,
    expected_artifact_name: str,
    expected_artifact_digest: str,
    expected_run_id: int,
    expected_repository_id: int,
    expected_source_sha: str,
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ValidationError("artifact metadata must be an object")

    artifact_id = positive_int(metadata.get("id"), "artifact id")
    artifact_name = canonical_string(metadata.get("name"), "artifact name")
    artifact_digest = canonical_string(metadata.get("digest"), "artifact digest")
    size = positive_int(metadata.get("size_in_bytes"), "artifact size")
    if metadata.get("expired") is not False:
        raise ValidationError("artifact must exist and not be expired")

    if artifact_id != expected_artifact_id:
        raise ValidationError("artifact id does not match producer output")
    if artifact_name != expected_artifact_name:
        raise ValidationError("artifact name does not match producer output")
    if not DIGEST_RE.fullmatch(expected_artifact_digest):
        raise ValidationError("expected artifact digest must be sha256:<64 lowercase hex>")
    if artifact_digest != expected_artifact_digest:
        raise ValidationError("artifact digest does not match producer output")

    workflow_run = metadata.get("workflow_run")
    if not isinstance(workflow_run, dict):
        raise ValidationError("artifact workflow_run must be an object")
    run_id = positive_int(workflow_run.get("id"), "artifact workflow run id")
    repository_id = positive_int(
        workflow_run.get("repository_id"), "artifact repository id"
    )
    head_repository_id = positive_int(
        workflow_run.get("head_repository_id"), "artifact head repository id"
    )
    source_sha = canonical_string(workflow_run.get("head_sha"), "artifact source SHA")

    if run_id != expected_run_id:
        raise ValidationError("artifact workflow run id does not match current run")
    if repository_id != expected_repository_id:
        raise ValidationError("artifact repository id does not match current repository")
    if head_repository_id != expected_repository_id:
        raise ValidationError(
            "artifact head repository id does not match current repository"
        )
    if not SHA_RE.fullmatch(expected_source_sha):
        raise ValidationError("expected source SHA must be 40 lowercase hex characters")
    if source_sha != expected_source_sha:
        raise ValidationError("artifact source SHA does not match current source")

    return {
        "artifactId": artifact_id,
        "artifactName": artifact_name,
        "artifactDigest": artifact_digest,
        "sizeInBytes": size,
        "runId": run_id,
        "repositoryId": repository_id,
        "sourceSHA": source_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an exact same-run GitHub Actions artifact handoff."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()

    try:
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        result = validate_current_run_artifact(
            metadata,
            expected_artifact_id=args.artifact_id,
            expected_artifact_name=args.artifact_name,
            expected_artifact_digest=args.artifact_digest,
            expected_run_id=args.run_id,
            expected_repository_id=args.repository_id,
            expected_source_sha=args.source_sha,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as error:
        print(error, file=sys.stderr)
        return 1

    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
