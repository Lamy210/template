from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator


class RegularFileSnapshotError(RuntimeError):
    pass


def copy_regular_file_bounded(
    source_path: Path,
    destination_path: Path,
    *,
    max_bytes: int,
) -> int:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise RegularFileSnapshotError(
            "copy byte limit must be a positive integer"
        )
    if not hasattr(os, "O_NOFOLLOW"):
        raise RegularFileSnapshotError("platform does not provide O_NOFOLLOW")
    if not destination_path.parent.is_dir() or destination_path.parent.is_symlink():
        raise RegularFileSnapshotError(
            f"destination parent must be a real directory: {destination_path.parent}"
        )
    if destination_path.exists() or destination_path.is_symlink():
        raise RegularFileSnapshotError(
            f"destination already exists: {destination_path}"
        )

    source_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        source_flags |= os.O_NONBLOCK

    try:
        source_descriptor = os.open(source_path, source_flags)
    except OSError as error:
        raise RegularFileSnapshotError(
            f"unable to open regular non-symlink file {source_path}: {error}"
        ) from error

    destination_descriptor: int | None = None
    created = False
    try:
        metadata = os.fstat(source_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RegularFileSnapshotError(
                f"input must be a regular non-symlink file: {source_path}"
            )
        if metadata.st_size > max_bytes:
            raise RegularFileSnapshotError(
                f"input exceeds copy byte limit: {metadata.st_size} > {max_bytes}"
            )

        destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            destination_flags |= os.O_NOFOLLOW
        try:
            destination_descriptor = os.open(
                destination_path,
                destination_flags,
                0o600,
            )
            created = True
        except OSError as error:
            raise RegularFileSnapshotError(
                f"unable to create bounded copy {destination_path}: {error}"
            ) from error

        copied_bytes = 0
        with os.fdopen(source_descriptor, "rb", closefd=False) as source:
            with os.fdopen(
                destination_descriptor,
                "wb",
                closefd=False,
            ) as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    copied_bytes += len(chunk)
                    if copied_bytes > max_bytes:
                        raise RegularFileSnapshotError(
                            "input grew beyond copy byte limit: "
                            f"{copied_bytes} > {max_bytes}"
                        )
                    destination.write(chunk)

        return copied_bytes
    except Exception:
        if created:
            try:
                destination_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        os.close(source_descriptor)


@contextmanager
def snapshot_regular_file(
    path: Path,
    *,
    prefix: str,
    max_bytes: int | None = None,
) -> Iterator[Path]:
    if max_bytes is not None and (type(max_bytes) is not int or max_bytes <= 0):
        raise RegularFileSnapshotError(
            "snapshot byte limit must be a positive integer"
        )
    if not hasattr(os, "O_NOFOLLOW"):
        raise RegularFileSnapshotError("platform does not provide O_NOFOLLOW")

    open_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        open_flags |= os.O_NONBLOCK

    try:
        descriptor = os.open(path, open_flags)
    except OSError as error:
        raise RegularFileSnapshotError(
            f"unable to open regular non-symlink file {path}: {error}"
        ) from error

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RegularFileSnapshotError(
                f"input must be a regular non-symlink file: {path}"
            )
        if max_bytes is not None and metadata.st_size > max_bytes:
            raise RegularFileSnapshotError(
                f"input exceeds snapshot byte limit: {metadata.st_size} > {max_bytes}"
            )

        with tempfile.TemporaryDirectory(prefix=prefix) as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot"
            try:
                copied_bytes = 0
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    with snapshot.open("xb") as destination:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            copied_bytes += len(chunk)
                            if max_bytes is not None and copied_bytes > max_bytes:
                                raise RegularFileSnapshotError(
                                    "input grew beyond snapshot byte limit: "
                                    f"{copied_bytes} > {max_bytes}"
                                )
                            destination.write(chunk)
                os.chmod(snapshot, 0o600)
            except OSError as error:
                raise RegularFileSnapshotError(
                    f"unable to snapshot regular file {path}: {error}"
                ) from error

            yield snapshot
    finally:
        os.close(descriptor)


__all__ = [
    "RegularFileSnapshotError",
    "copy_regular_file_bounded",
    "snapshot_regular_file",
]
