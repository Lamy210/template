from __future__ import annotations

import os
from pathlib import Path
import tempfile

from scripts.release.atomic_directory_publish import (
    AtomicDirectoryPublishError,
    atomic_publish_directory_noreplace,
)
from scripts.release.release_asset_limits import release_asset_size_limit
from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    copy_regular_file_bounded,
)
from scripts.release.verified_release_payload import validate_verified_release_payload


def prepare_verified_release_handoff(
    source_root: Path,
    output_dir: Path,
    *,
    dmg_name: str,
) -> list[str]:
    source_errors = validate_verified_release_payload(source_root, dmg_name)
    if source_errors:
        return source_errors

    if output_dir.exists() or output_dir.is_symlink():
        return [
            f"verified release handoff output must not already exist: {output_dir}"
        ]
    if not output_dir.parent.is_dir() or output_dir.parent.is_symlink():
        return [
            "verified release handoff output parent must be a real directory: "
            f"{output_dir.parent}"
        ]

    expected_names = (
        dmg_name,
        f"{dmg_name}.sha256",
        "release-provenance.json",
    )

    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{output_dir.name}.",
            dir=output_dir.parent,
        ) as temporary_directory:
            stage = Path(temporary_directory) / "payload"
            stage.mkdir(mode=0o700)

            for name in expected_names:
                limit = release_asset_size_limit(name, dmg_name=dmg_name)
                if limit is None:
                    return [
                        f"verified release handoff entry has unsupported role: {name}"
                    ]
                copy_regular_file_bounded(
                    source_root / name,
                    stage / name,
                    max_bytes=limit,
                )

            staged_errors = validate_verified_release_payload(stage, dmg_name)
            if staged_errors:
                return [
                    f"staged verified release handoff is invalid: {error}"
                    for error in staged_errors
                ]

            for name in expected_names:
                os.chmod(stage / name, 0o400)

            atomic_publish_directory_noreplace(stage, output_dir)
    except (RegularFileSnapshotError, AtomicDirectoryPublishError, OSError) as error:
        return [f"unable to prepare verified release handoff snapshot: {error}"]

    return []


__all__ = ["prepare_verified_release_handoff"]
