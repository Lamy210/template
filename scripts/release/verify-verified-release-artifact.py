#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.verified_release_artifact import verify_verified_release_artifact


def load_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(
            f"failed to read verified release artifact metadata {path}: {error}"
        ) from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the exact signer-produced artifact before repository publication."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--publisher-run-id", required=True, type=int)
    parser.add_argument("--publisher-run-attempt", required=True, type=int)
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    args = parser.parse_args()

    errors = verify_verified_release_artifact(
        artifact_metadata=load_json(args.metadata),
        artifact_id=args.artifact_id,
        artifact_name=args.artifact_name,
        artifact_digest=args.artifact_digest,
        publisher_run_id=args.publisher_run_id,
        publisher_run_attempt=args.publisher_run_attempt,
        publisher_sha=args.publisher_sha,
        repository_id=args.repository_id,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
