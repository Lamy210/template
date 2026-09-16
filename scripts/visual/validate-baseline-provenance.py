#!/usr/bin/env python3
"""Cross-check trusted resolver metadata against a visual baseline bundle."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
ALLOWED_TRUSTED_EVENTS = {"push", "schedule"}


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _validate_expected_events(expected_events: tuple[str, ...]) -> tuple[str, ...]:
    if not expected_events:
        raise ValueError("expected trusted events must not be empty")
    if len(set(expected_events)) != len(expected_events):
        raise ValueError("expected trusted events must not contain duplicates")
    for event in expected_events:
        if event not in ALLOWED_TRUSTED_EVENTS:
            raise ValueError(f"unsupported expected trusted event: {event}")
    return expected_events


def _parse_expected_events(value: str) -> tuple[str, ...]:
    if not value:
        raise ValueError("expected trusted events must not be empty")
    return _validate_expected_events(tuple(value.split(",")))


def validate_provenance(
    *,
    resolver_metadata_path: Path,
    bundle_manifest_path: Path,
    expected_repository: str,
    expected_workflow: str,
    expected_artifact: str,
    expected_events: tuple[str, ...] = ("push",),
) -> dict[str, Any]:
    expected_events = _validate_expected_events(expected_events)
    resolver = _load_object(resolver_metadata_path, "resolver metadata")
    bundle = _load_object(bundle_manifest_path, "bundle manifest")

    if resolver.get("schemaVersion") != 1:
        raise ValueError("resolver metadata schemaVersion must be 1")
    if bundle.get("schemaVersion") != 1:
        raise ValueError("bundle manifest schemaVersion must be 1")

    repository = _non_empty_string(resolver.get("repository"), "resolver repository")
    workflow = _non_empty_string(resolver.get("workflow"), "resolver workflow")
    artifact = _non_empty_string(resolver.get("artifactName"), "resolver artifact name")
    branch = _non_empty_string(resolver.get("branch"), "resolver branch")
    event = _non_empty_string(resolver.get("event"), "resolver event")
    run_id = _positive_int(resolver.get("runId"), "resolver run id")
    run_attempt = _positive_int(resolver.get("runAttempt"), "resolver run attempt")
    source_sha = _non_empty_string(resolver.get("sourceSHA"), "resolver source SHA")
    artifact_digest = _non_empty_string(
        resolver.get("artifactDigest"), "resolver artifact digest"
    )

    if repository != expected_repository:
        raise ValueError("resolver repository does not match expected repository")
    if workflow != expected_workflow:
        raise ValueError("resolver workflow does not match expected workflow")
    if artifact != expected_artifact:
        raise ValueError("resolver artifact does not match expected artifact")
    if branch != "main":
        raise ValueError("resolver branch must be main")
    if event not in expected_events:
        raise ValueError("resolver event is outside the expected trusted event policy")
    if not GIT_SHA_RE.fullmatch(source_sha):
        raise ValueError("resolver source SHA is malformed")
    if not SHA256_RE.fullmatch(artifact_digest):
        raise ValueError("resolver artifact digest is malformed")

    bundle_repository = _non_empty_string(
        bundle.get("sourceRepository"), "bundle repository"
    )
    bundle_workflow = _non_empty_string(bundle.get("workflow"), "bundle workflow")
    bundle_run_id = _non_empty_string(bundle.get("sourceRunID"), "bundle run id")
    bundle_attempt = _positive_int(bundle.get("runAttempt"), "bundle run attempt")
    bundle_sha = _non_empty_string(bundle.get("sourceSHA"), "bundle source SHA")

    if bundle_repository != repository:
        raise ValueError("bundle repository does not match resolver repository")
    if bundle_workflow != workflow:
        raise ValueError("bundle workflow does not match resolver workflow")
    if bundle_run_id != str(run_id):
        raise ValueError("bundle source run does not match resolver run")
    if bundle_attempt != run_attempt:
        raise ValueError("bundle run attempt does not match resolver run attempt")
    if bundle_sha != source_sha:
        raise ValueError("bundle source SHA does not match resolver source SHA")

    return {
        "repository": repository,
        "workflow": workflow,
        "artifactName": artifact,
        "event": event,
        "runId": run_id,
        "runAttempt": run_attempt,
        "sourceSHA": source_sha,
        "artifactDigest": artifact_digest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolver-metadata", required=True, type=Path)
    parser.add_argument("--bundle-manifest", required=True, type=Path)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-workflow", required=True)
    parser.add_argument("--expected-artifact", required=True)
    parser.add_argument("--expected-events", default="push")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        expected_events = _parse_expected_events(args.expected_events)
        result = validate_provenance(
            resolver_metadata_path=args.resolver_metadata,
            bundle_manifest_path=args.bundle_manifest,
            expected_repository=args.expected_repository,
            expected_workflow=args.expected_workflow,
            expected_artifact=args.expected_artifact,
            expected_events=expected_events,
        )
    except ValueError as exc:
        print(f"validate-baseline-provenance: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
