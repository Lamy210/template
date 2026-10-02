from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Iterator


class RegularFileSnapshotError(RuntimeError):
    pass


@contextmanager
def snapshot_regular_file(
    path: Path,
    *,
    prefix: str,
) -> Iterator[Path]:
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

        with tempfile.TemporaryDirectory(prefix=prefix) as temporary_directory:
            snapshot = Path(temporary_directory) / "snapshot"
            try:
                with os.fdopen(descriptor, "rb", closefd=False) as source:
                    with snapshot.open("xb") as destination:
                        shutil.copyfileobj(
                            source,
                            destination,
                            length=1024 * 1024,
                        )
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
    "snapshot_regular_file",
]
