from __future__ import annotations

import os
from pathlib import Path
import stat


def validate_cask_output_path(*, root: Path, output: Path) -> list[str]:
    errors: list[str] = []

    raw_output = os.fspath(output)
    if ".." in Path(raw_output).parts:
        errors.append("Cask output path must not contain parent traversal")

    root_abs = Path(os.path.abspath(os.fspath(root)))
    output_abs = Path(os.path.abspath(raw_output))

    if not os.path.lexists(root_abs):
        errors.append(f"Cask output root does not exist: {root_abs}")
        return errors

    root_mode = os.lstat(root_abs).st_mode
    if stat.S_ISLNK(root_mode):
        errors.append(f"Cask output root must not be a symlink: {root_abs}")
        return errors
    if not stat.S_ISDIR(root_mode):
        errors.append(f"Cask output root must be a directory: {root_abs}")
        return errors

    try:
        relative = output_abs.relative_to(root_abs)
    except ValueError:
        errors.append("Cask output must remain inside the configured output root")
        return errors

    if relative == Path("."):
        errors.append("Cask output must name a file below the configured output root")
        return errors

    current = root_abs
    parts = relative.parts
    for index, part in enumerate(parts):
        current = current / part
        if not os.path.lexists(current):
            continue

        mode = os.lstat(current).st_mode
        is_target = index == len(parts) - 1
        if stat.S_ISLNK(mode):
            errors.append(f"Cask output path must not traverse a symlink: {current}")
            continue
        if is_target:
            if not stat.S_ISREG(mode):
                errors.append(f"Existing Cask output must be a regular file: {current}")
        elif not stat.S_ISDIR(mode):
            errors.append(f"Cask output parent must be a directory: {current}")

    return errors
