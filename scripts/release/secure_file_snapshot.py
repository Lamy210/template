from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator


class RegularFileSnapshotError(RuntimeError):
    pass


def _open_directory_nofollow(path: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RegularFileSnapshotError(
            "platform does not provide O_NOFOLLOW/O_DIRECTORY"
        )

    absolute = Path(os.path.abspath(path))
    if absolute.anchor != os.sep:
        raise RegularFileSnapshotError(
            f"directory path must resolve to an absolute POSIX path: {path}"
        )

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(os.sep, flags)
        for component in absolute.parts[1:]:
            if component in {"", ".", ".."}:
                raise RegularFileSnapshotError(
                    f"directory path contains an unsafe component: {path}"
                )
            next_descriptor = os.open(
                component,
                flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except RegularFileSnapshotError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise RegularFileSnapshotError(
            f"unable to open directory without following symlinks {path}: {error}"
        ) from error


def _open_regular_file_nofollow(path: Path) -> int:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RegularFileSnapshotError(
            "platform does not provide O_NOFOLLOW/O_DIRECTORY"
        )

    absolute = Path(os.path.abspath(path))
    if absolute.name in {"", ".", ".."}:
        raise RegularFileSnapshotError(
            f"input must name a file: {path}"
        )

    try:
        resolved_parent = absolute.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise RegularFileSnapshotError(
            f"unable to resolve input parent {path.parent}: {error}"
        ) from error

    parent_descriptor = _open_directory_nofollow(resolved_parent)
    open_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        open_flags |= os.O_NONBLOCK

    try:
        return os.open(
            absolute.name,
            open_flags,
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise RegularFileSnapshotError(
            f"unable to open regular non-symlink file {path}: {error}"
        ) from error
    finally:
        os.close(parent_descriptor)


def _open_destination_parent(path: Path) -> tuple[int, os.stat_result]:
    absolute = Path(os.path.abspath(path))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    if absolute == Path(os.sep):
        descriptor = _open_directory_nofollow(absolute)
    else:
        try:
            resolved_ancestor = absolute.parent.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise RegularFileSnapshotError(
                f"unable to resolve destination parent ancestor {path}: {error}"
            ) from error

        ancestor_descriptor = _open_directory_nofollow(resolved_ancestor)
        try:
            descriptor = os.open(
                absolute.name,
                flags,
                dir_fd=ancestor_descriptor,
            )
        except OSError as error:
            raise RegularFileSnapshotError(
                f"destination parent must be a real directory: {path}: {error}"
            ) from error
        finally:
            os.close(ancestor_descriptor)

    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        os.close(descriptor)
        raise RegularFileSnapshotError(
            f"unable to inspect destination parent {path}: {error}"
        ) from error
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise RegularFileSnapshotError(
            f"destination parent must be a directory: {path}"
        )
    return descriptor, metadata


def _assert_destination_parent_identity(
    path: Path,
    expected: os.stat_result,
) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise RegularFileSnapshotError(
            f"destination parent changed after validation: {path}: {error}"
        ) from error

    if (
        not stat.S_ISDIR(current.st_mode)
        or current.st_dev != expected.st_dev
        or current.st_ino != expected.st_ino
    ):
        raise RegularFileSnapshotError(
            f"destination parent changed after validation: {path}"
        )


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
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RegularFileSnapshotError(
            "platform does not provide O_NOFOLLOW/O_DIRECTORY"
        )
    if destination_path.name in {"", ".", ".."}:
        raise RegularFileSnapshotError(
            f"destination must name a file: {destination_path}"
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

    destination_parent_descriptor: int | None = None
    destination_descriptor: int | None = None
    created = False
    try:
        (
            destination_parent_descriptor,
            destination_parent_metadata,
        ) = _open_destination_parent(destination_path.parent)

        try:
            os.stat(
                destination_path.name,
                dir_fd=destination_parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError as error:
            raise RegularFileSnapshotError(
                f"unable to inspect destination {destination_path}: {error}"
            ) from error
        else:
            raise RegularFileSnapshotError(
                f"destination already exists: {destination_path}"
            )

        metadata = os.fstat(source_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RegularFileSnapshotError(
                f"input must be a regular non-symlink file: {source_path}"
            )
        if metadata.st_size > max_bytes:
            raise RegularFileSnapshotError(
                f"input exceeds copy byte limit: {metadata.st_size} > {max_bytes}"
            )

        _assert_destination_parent_identity(
            destination_path.parent,
            destination_parent_metadata,
        )

        destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            destination_descriptor = os.open(
                destination_path.name,
                destination_flags,
                0o600,
                dir_fd=destination_parent_descriptor,
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

        _assert_destination_parent_identity(
            destination_path.parent,
            destination_parent_metadata,
        )
        return copied_bytes
    except Exception:
        if created and destination_parent_descriptor is not None:
            try:
                os.unlink(
                    destination_path.name,
                    dir_fd=destination_parent_descriptor,
                )
            except OSError:
                pass
        raise
    finally:
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        if destination_parent_descriptor is not None:
            os.close(destination_parent_descriptor)
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

    descriptor = _open_regular_file_nofollow(path)

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
