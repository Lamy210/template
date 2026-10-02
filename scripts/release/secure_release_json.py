from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from scripts.release.release_asset_limits import MAX_RELEASE_METADATA_BYTES
from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    snapshot_regular_file,
)


class SecureReleaseJsonError(RuntimeError):
    pass


def load_bounded_release_json(
    path: Path,
    *,
    label: str,
    max_bytes: int = MAX_RELEASE_METADATA_BYTES,
) -> object:
    try:
        with snapshot_regular_file(
            path,
            prefix="release-json.",
            max_bytes=max_bytes,
        ) as snapshot:
            payload = snapshot.read_text(encoding="utf-8")
    except (RegularFileSnapshotError, OSError, UnicodeError) as error:
        raise SecureReleaseJsonError(
            f"failed to read {label} {path}: {error}"
        ) from error

    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise SecureReleaseJsonError(
            f"failed to parse {label} {path}: {error}"
        ) from error


def write_release_json_exclusive(
    path: Path,
    document: object,
    *,
    label: str,
) -> None:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise SecureReleaseJsonError(
            "platform does not provide O_NOFOLLOW/O_DIRECTORY"
        )
    if path.name in {"", ".", ".."}:
        raise SecureReleaseJsonError(f"invalid {label} output basename: {path}")
    if path.exists() or path.is_symlink():
        raise SecureReleaseJsonError(
            f"{label} output already exists: {path}"
        )

    parent_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        parent_descriptor = os.open(path.parent, parent_flags)
    except OSError as error:
        raise SecureReleaseJsonError(
            f"{label} output parent must be a real directory: "
            f"{path.parent}: {error}"
        ) from error

    descriptor: int | None = None
    created = False
    try:
        metadata = os.fstat(parent_descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise SecureReleaseJsonError(
                f"{label} output parent must be a directory: {path.parent}"
            )

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            descriptor = os.open(
                path.name,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
            created = True
        except OSError as error:
            raise SecureReleaseJsonError(
                f"unable to create exclusive {label} output {path}: {error}"
            ) from error

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
                closefd=False,
            ) as handle:
                json.dump(
                    document,
                    handle,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(descriptor)
        except (OSError, TypeError, ValueError) as error:
            raise SecureReleaseJsonError(
                f"unable to write {label} output {path}: {error}"
            ) from error
    except Exception:
        if created:
            try:
                os.unlink(path.name, dir_fd=parent_descriptor)
            except OSError:
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_descriptor)


__all__ = [
    "SecureReleaseJsonError",
    "load_bounded_release_json",
    "write_release_json_exclusive",
]
