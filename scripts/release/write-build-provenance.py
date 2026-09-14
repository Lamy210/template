#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.release.release_provenance import ExpectedBuild, build_provenance


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write canonical release build provenance.")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--archive-path", required=True, type=Path)
    parser.add_argument("--app-basename", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archive_path = args.archive_path
    if not archive_path.is_file():
        raise SystemExit(f"archive not found: {archive_path}")

    artifact_name = f"unsigned-macos-release-{args.run_id}-{args.run_attempt}"
    version = args.tag[1:] if args.tag.startswith("v") else ""
    expected = ExpectedBuild(
        repository=args.repository,
        workflow_name=args.workflow_name,
        workflow_path=args.workflow_path,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        source_event="push",
        source_sha=args.source_sha,
        source_ref=f"refs/tags/{args.tag}",
        tag=args.tag,
        artifact_name=artifact_name,
        archive_name=archive_path.name,
        app_basename=args.app_basename,
        bundle_id=args.bundle_id,
        version=version,
    )
    document = build_provenance(expected, sha256_file(archive_path))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
