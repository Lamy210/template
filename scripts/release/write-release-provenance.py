#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from release_attestation import ExpectedRelease, build_release_attestation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write canonical final release provenance.")
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--source-run-attempt", required=True, type=int)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-artifact-id", required=True, type=int)
    parser.add_argument("--source-artifact-digest", required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--publisher-run-id", required=True, type=int)
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--dmg-path", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected = ExpectedRelease(
        source_repository=args.source_repository,
        source_run_id=args.source_run_id,
        source_run_attempt=args.source_run_attempt,
        source_sha=args.source_sha,
        tag=args.tag,
        source_artifact_id=args.source_artifact_id,
        source_artifact_digest=args.source_artifact_digest,
        archive_sha256=args.archive_sha256,
        publisher_run_id=args.publisher_run_id,
        publisher_sha=args.publisher_sha,
        dmg_path=args.dmg_path,
    )
    document = build_release_attestation(expected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
