#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from validated_release_metadata import ExpectedValidatedRelease, verify_validated_release_metadata


def load_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"failed to read validated release metadata {path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Reverify publisher-owned release metadata before secrets.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--source-run-attempt", required=True, type=int)
    parser.add_argument("--source-artifact-id", required=True, type=int)
    parser.add_argument("--source-artifact-digest", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--publisher-run-id", required=True, type=int)
    parser.add_argument("--publisher-run-attempt", required=True, type=int)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--app-basename", required=True)
    parser.add_argument("--bundle-id", required=True)
    args = parser.parse_args()

    expected = ExpectedValidatedRelease(
        source_repository=args.repository,
        source_run_id=args.source_run_id,
        source_run_attempt=args.source_run_attempt,
        source_artifact_id=args.source_artifact_id,
        source_artifact_digest=args.source_artifact_digest,
        source_sha=args.source_sha,
        source_tag=args.source_tag,
        source_version=args.source_version,
        publisher_sha=args.publisher_sha,
        publisher_run_id=args.publisher_run_id,
        publisher_run_attempt=args.publisher_run_attempt,
        archive_sha256=args.archive_sha256,
        app_basename=args.app_basename,
        bundle_id=args.bundle_id,
    )
    errors = verify_validated_release_metadata(load_json(args.metadata), args.archive, expected)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
