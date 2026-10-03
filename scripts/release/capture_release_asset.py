from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
from typing import BinaryIO


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.secure_file_snapshot import (  # noqa: E402
    RegularFileSnapshotError,
    _assert_destination_parent_identity,
    _open_destination_parent,
)


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CHUNK_SIZE = 1024 * 1024


class ReleaseAssetCaptureError(RuntimeError):
    pass


def capture_release_asset(
    source: BinaryIO,
    output_path: Path,
    *,
    expected_size: int,
    expected_digest: str,
) -> None:
    if type(expected_size) is not int or expected_size <= 0:
        raise ReleaseAssetCaptureError("expected size must be a positive integer")
    if (
        not isinstance(expected_digest, str)
        or DIGEST_RE.fullmatch(expected_digest) is None
    ):
        raise ReleaseAssetCaptureError(
            "expected digest must use sha256:<64 lowercase hex>"
        )
    if output_path.exists() or output_path.is_symlink():
        raise ReleaseAssetCaptureError(
            f"output path already exists: {output_path}"
        )
    if not output_path.parent.is_dir() or output_path.parent.is_symlink():
        raise ReleaseAssetCaptureError(
            f"output parent must be a real directory: {output_path.parent}"
        )

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    parent_descriptor: int | None = None
    descriptor: int | None = None
    created = False
    try:
        try:
            (
                parent_descriptor,
                parent_metadata,
            ) = _open_destination_parent(output_path.parent)

            try:
                os.stat(
                    output_path.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            except OSError as error:
                raise ReleaseAssetCaptureError(
                    f"unable to inspect asset output {output_path}: {error}"
                ) from error
            else:
                raise ReleaseAssetCaptureError(
                    f"output path already exists: {output_path}"
                )

            _assert_destination_parent_identity(
                output_path.parent,
                parent_metadata,
            )

            try:
                descriptor = os.open(
                    output_path.name,
                    flags,
                    0o600,
                    dir_fd=parent_descriptor,
                )
                created = True
            except OSError as error:
                raise ReleaseAssetCaptureError(
                    f"unable to create bounded asset output {output_path}: {error}"
                ) from error

            _assert_destination_parent_identity(
                output_path.parent,
                parent_metadata,
            )
        except RegularFileSnapshotError as error:
            raise ReleaseAssetCaptureError(str(error)) from error

        digest = hashlib.sha256()
        copied = 0
        with os.fdopen(descriptor, "wb", closefd=False) as destination:
            while True:
                chunk = source.read(CHUNK_SIZE)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > expected_size:
                    raise ReleaseAssetCaptureError(
                        "downloaded release asset exceeded expected size: "
                        f"{copied} > {expected_size}"
                    )
                digest.update(chunk)
                destination.write(chunk)

        if copied != expected_size:
            raise ReleaseAssetCaptureError(
                "downloaded release asset size mismatch: "
                f"{copied} != {expected_size}"
            )

        actual_digest = "sha256:" + digest.hexdigest()
        if actual_digest != expected_digest:
            raise ReleaseAssetCaptureError(
                "downloaded release asset digest mismatch: "
                f"expected {expected_digest}, got {actual_digest}"
            )

        try:
            _assert_destination_parent_identity(
                output_path.parent,
                parent_metadata,
            )
        except RegularFileSnapshotError as error:
            raise ReleaseAssetCaptureError(str(error)) from error
    except Exception:
        if created and parent_descriptor is not None:
            try:
                os.unlink(
                    output_path.name,
                    dir_fd=parent_descriptor,
                )
            except OSError:
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one release asset from stdin with exact size and SHA-256 bounds."
        )
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-size", required=True, type=int)
    parser.add_argument("--expected-digest", required=True)
    args = parser.parse_args(argv)

    try:
        capture_release_asset(
            sys.stdin.buffer,
            args.output,
            expected_size=args.expected_size,
            expected_digest=args.expected_digest,
        )
    except ReleaseAssetCaptureError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
