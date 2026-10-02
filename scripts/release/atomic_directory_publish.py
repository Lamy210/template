from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import sys


class AtomicDirectoryPublishError(RuntimeError):
    pass


def _raise_native_error(operation: str) -> None:
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise AtomicDirectoryPublishError(
            "destination already exists; refusing to replace it"
        )
    raise AtomicDirectoryPublishError(
        f"{operation} failed: {os.strerror(error_number)}"
    )


def _linux_publish(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise AtomicDirectoryPublishError(
            "platform libc does not provide renameat2(RENAME_NOREPLACE)"
        )

    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int

    at_fdcwd = -100
    rename_noreplace = 1
    if (
        renameat2(
            at_fdcwd,
            os.fsencode(source),
            at_fdcwd,
            os.fsencode(destination),
            rename_noreplace,
        )
        != 0
    ):
        _raise_native_error("renameat2(RENAME_NOREPLACE)")


def _darwin_publish(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renamex_np = getattr(libc, "renamex_np", None)
    if renamex_np is None:
        raise AtomicDirectoryPublishError(
            "platform libc does not provide renamex_np(RENAME_EXCL)"
        )

    renamex_np.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renamex_np.restype = ctypes.c_int

    rename_excl = 0x00000004
    if renamex_np(
        os.fsencode(source),
        os.fsencode(destination),
        rename_excl,
    ) != 0:
        _raise_native_error("renamex_np(RENAME_EXCL)")


def atomic_publish_directory_noreplace(
    source: Path,
    destination: Path,
) -> None:
    if not source.is_dir() or source.is_symlink():
        raise AtomicDirectoryPublishError(
            f"source must be a real directory: {source}"
        )
    if destination.exists() or destination.is_symlink():
        raise AtomicDirectoryPublishError(
            f"destination already exists; refusing to replace it: {destination}"
        )
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise AtomicDirectoryPublishError(
            f"destination parent must be a real directory: {destination.parent}"
        )

    if sys.platform.startswith("linux"):
        _linux_publish(source, destination)
    elif sys.platform == "darwin":
        _darwin_publish(source, destination)
    else:
        raise AtomicDirectoryPublishError(
            f"atomic no-replace directory publication is unsupported on {sys.platform}"
        )


__all__ = [
    "AtomicDirectoryPublishError",
    "atomic_publish_directory_noreplace",
]
