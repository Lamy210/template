#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from release_attestation import ExpectedRelease, verify_release_attestation


def load_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"failed to read final release provenance {path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reverify final release provenance before GitHub publication."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--dmg", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--source-run-attempt", required=True, type=int)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--source-artifact-id", required=True, type=int)
    parser.add_argument("--source-artifact-digest", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--publisher-run-id", required=True, type=int)
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--app-basename", required=True)
    parser.add_argument("--bundle-id", required=True)
    args = parser.parse_args()

    expected = ExpectedRelease(
        source_repository=args.repository,
        source_run_id=args.source_run_id,
        source_run_attempt=args.source_run_attempt,
        source_sha=args.source_sha,
        tag=args.source_tag,
        source_artifact_id=args.source_artifact_id,
        source_artifact_digest=args.source_artifact_digest,
        archive_sha256=args.archive_sha256,
        publisher_run_id=args.publisher_run_id,
        publisher_sha=args.publisher_sha,
        app_basename=args.app_basename,
        bundle_id=args.bundle_id,
        dmg_path=args.dmg,
    )
    errors = verify_release_attestation(load_json(args.metadata), expected)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
