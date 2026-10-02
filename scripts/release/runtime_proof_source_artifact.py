from __future__ import annotations

import hashlib
from pathlib import Path
import re

from scripts.release.actions_artifact import validate_and_extract_release_artifact
from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    snapshot_regular_file,
)


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
APP_ARCHIVE_PATH = Path("release-input/unsigned-macos-app.tar.gz")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def verify_runtime_proof_source_artifact(
    archive_path: Path,
    output_dir: Path,
    *,
    expected_artifact_digest: object,
    expected_app_archive_digest: object,
) -> list[str]:
    errors: list[str] = []

    if (
        not isinstance(expected_artifact_digest, str)
        or DIGEST_RE.fullmatch(expected_artifact_digest) is None
    ):
        errors.append("expected source artifact digest must use sha256:<64 lowercase hex>")
    if (
        not isinstance(expected_app_archive_digest, str)
        or DIGEST_RE.fullmatch(expected_app_archive_digest) is None
    ):
        errors.append(
            "expected source unsigned app archive digest must use sha256:<64 lowercase hex>"
        )
    if errors:
        return errors

    if archive_path.is_symlink() or not archive_path.is_file():
        return [
            f"source Artifact ZIP must be a regular non-symlink file: {archive_path}"
        ]

    try:
        with snapshot_regular_file(
            archive_path,
            prefix="runtime-proof-source-artifact.",
        ) as snapshot_path:
            actual_artifact_digest = _sha256_file(snapshot_path)
            if actual_artifact_digest != expected_artifact_digest:
                return [
                    "source Artifact ZIP digest mismatch: "
                    f"expected {expected_artifact_digest}, got {actual_artifact_digest}"
                ]

            extraction_errors = validate_and_extract_release_artifact(
                snapshot_path,
                output_dir,
            )
            if extraction_errors:
                return [
                    f"source Artifact payload: {error}"
                    for error in extraction_errors
                ]
    except RegularFileSnapshotError as error:
        return [f"unable to snapshot source Artifact ZIP: {error}"]

    app_archive_path = output_dir / APP_ARCHIVE_PATH
    try:
        with snapshot_regular_file(
            app_archive_path,
            prefix="runtime-proof-source-app.",
        ) as app_snapshot_path:
            actual_app_archive_digest = _sha256_file(app_snapshot_path)
    except RegularFileSnapshotError as error:
        return [f"unable to snapshot source unsigned app archive: {error}"]

    if actual_app_archive_digest != expected_app_archive_digest:
        return [
            "source unsigned app archive digest mismatch: "
            f"expected {expected_app_archive_digest}, got {actual_app_archive_digest}"
        ]

    return []
