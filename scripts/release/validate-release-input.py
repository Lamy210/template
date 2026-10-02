#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.release_input import validate_release_input
from scripts.release.secure_release_json import (
    SecureReleaseJsonError,
    load_bounded_release_json,
    write_release_json_exclusive,
)


def load_json(path: Path, *, label: str) -> object:
    try:
        return load_bounded_release_json(path, label=label)
    except SecureReleaseJsonError as error:
        raise SystemExit(str(error)) from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release input before privileged signing.")
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--source-metadata", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--app-basename", required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--resolved-tag-sha", required=True)
    parser.add_argument("--source-is-ancestor", required=True, choices=("true", "false"))
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--publisher-run-id", required=True, type=int)
    parser.add_argument("--publisher-run-attempt", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    errors, validated = validate_release_input(
        provenance_document=load_json(
            args.provenance,
            label="build provenance",
        ),
        source_metadata=load_json(
            args.source_metadata,
            label="source artifact metadata",
        ),
        archive_path=args.archive,
        expected_repository=args.repository,
        expected_workflow_path=args.workflow_path,
        expected_app_basename=args.app_basename,
        expected_bundle_id=args.bundle_id,
        resolved_tag_sha=args.resolved_tag_sha,
        source_is_ancestor=args.source_is_ancestor == "true",
        publisher_sha=args.publisher_sha,
        publisher_run_id=args.publisher_run_id,
        publisher_run_attempt=args.publisher_run_attempt,
        release_scripts_root=Path(__file__).resolve().parent,
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    assert validated is not None
    try:
        write_release_json_exclusive(
            args.output,
            validated,
            label="validated release metadata",
        )
    except SecureReleaseJsonError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
