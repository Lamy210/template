from __future__ import annotations

import json
import os
from pathlib import Path
import stat


DEFAULT_MAX_JSON_BYTES = 2 * 1024 * 1024


class BoundedJsonError(RuntimeError):
    pass


def load_bounded_json_file(
    path: Path,
    *,
    label: str,
    max_bytes: int = DEFAULT_MAX_JSON_BYTES,
) -> object:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise BoundedJsonError("JSON byte limit must be a positive integer")
    if not hasattr(os, "O_NOFOLLOW"):
        raise BoundedJsonError("platform does not provide O_NOFOLLOW")

    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise BoundedJsonError(
            f"failed to open {label} {path} as a regular non-symlink file: {error}"
        ) from error

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise BoundedJsonError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        if metadata.st_size > max_bytes:
            raise BoundedJsonError(
                f"{label} exceeds JSON byte limit: {metadata.st_size} > {max_bytes}"
            )

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise BoundedJsonError(
                    f"{label} exceeds JSON byte limit while reading: {total} > {max_bytes}"
                )
            chunks.append(chunk)
    except OSError as error:
        raise BoundedJsonError(f"failed to read {label} {path}: {error}") from error
    finally:
        os.close(descriptor)

    try:
        payload = b"".join(chunks).decode("utf-8")
    except UnicodeError as error:
        raise BoundedJsonError(f"failed to decode {label} {path} as UTF-8: {error}") from error

    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise BoundedJsonError(f"failed to parse {label} {path}: {error}") from error


__all__ = [
    "BoundedJsonError",
    "DEFAULT_MAX_JSON_BYTES",
    "load_bounded_json_file",
]
