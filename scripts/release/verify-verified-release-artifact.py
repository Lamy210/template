#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.bounded_json import (  # noqa: E402
    BoundedJsonError,
    load_bounded_json_file,
)
from scripts.release.verified_release_artifact import (  # noqa: E402
    verify_verified_release_artifact,
)


def write_positive_integer_output(path: Path, value: int) -> None:
    if type(value) is not int or value <= 0:
        raise OSError("output value must be a positive integer")
    if path.exists() or path.is_symlink():
        raise OSError(f"output path already exists: {path}")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise OSError(f"output parent must be a real directory: {path.parent}")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as handle:
            handle.write(f"{value}\n")
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def load_json(path: Path) -> object:
    try:
        return load_bounded_json_file(path, label="verified release artifact metadata")
    except BoundedJsonError as error:
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
    parser.add_argument("--size-output", type=Path)
    args = parser.parse_args()

    artifact_metadata = load_json(args.metadata)
    errors = verify_verified_release_artifact(
        artifact_metadata=artifact_metadata,
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

    if args.size_output is not None:
        assert isinstance(artifact_metadata, dict)
        size = artifact_metadata["size_in_bytes"]
        assert type(size) is int and size > 0
        try:
            write_positive_integer_output(args.size_output, size)
        except OSError as error:
            print(
                f"failed to write verified release artifact size: {error}",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
