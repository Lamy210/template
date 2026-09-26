from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from scripts.release.actions_artifact import MAX_APP_ARCHIVE_BYTES


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
METADATA_NAME = "validated-release-metadata.json"
APP_ARCHIVE_NAME = "unsigned-macos-app.tar.gz"
DEFAULT_MAX_METADATA_BYTES = 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    if info.create_system != 3:
        return False
    file_type = (info.external_attr >> 16) & stat.S_IFMT(0o170000)
    return file_type == stat.S_IFLNK


def extract_runtime_proof_metadata(
    archive_path: Path,
    output_path: Path,
    *,
    expected_digest: str,
    app_archive_digest_output_path: Path | None = None,
    max_metadata_bytes: int = DEFAULT_MAX_METADATA_BYTES,
    max_app_archive_bytes: int = MAX_APP_ARCHIVE_BYTES,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(expected_digest, str) or DIGEST_RE.fullmatch(expected_digest) is None:
        return ["expected artifact digest must use sha256:<64 lowercase hex>"]
    if type(max_metadata_bytes) is not int or max_metadata_bytes <= 0:
        return ["max metadata size must be a positive integer"]
    if type(max_app_archive_bytes) is not int or max_app_archive_bytes <= 0:
        return ["max unsigned app archive size must be a positive integer"]
    if archive_path.is_symlink() or not archive_path.is_file():
        return [f"runtime proof artifact ZIP must be a regular non-symlink file: {archive_path}"]
    if output_path.exists():
        return [f"runtime proof metadata output must not already exist: {output_path}"]
    if (
        app_archive_digest_output_path is not None
        and app_archive_digest_output_path.exists()
    ):
        return [
            "runtime proof archive digest output must not already exist: "
            f"{app_archive_digest_output_path}"
        ]

    actual_digest = _sha256_file(archive_path)
    if actual_digest != expected_digest:
        return [
            "runtime proof artifact ZIP digest mismatch: "
            f"expected {expected_digest}, got {actual_digest}"
        ]

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            nested_metadata = [
                info
                for info in infos
                if not info.is_dir()
                and PurePosixPath(info.filename).name == METADATA_NAME
                and info.filename != METADATA_NAME
            ]
            if nested_metadata:
                errors.append(
                    "runtime proof metadata must be a root-level Artifact entry"
                )

            metadata_candidates = [
                info
                for info in infos
                if not info.is_dir() and info.filename == METADATA_NAME
            ]
            if len(metadata_candidates) != 1:
                errors.append(
                    f"runtime proof artifact must contain exactly one {METADATA_NAME}; "
                    f"found {len(metadata_candidates)}"
                )

            app_candidates = [
                info
                for info in infos
                if not info.is_dir() and info.filename == APP_ARCHIVE_NAME
            ]
            if len(app_candidates) != 1:
                errors.append(
                    "runtime proof artifact must contain exactly one root-level "
                    f"unsigned app archive {APP_ARCHIVE_NAME}; found {len(app_candidates)}"
                )

            if errors:
                return errors

            info = metadata_candidates[0]
            app_info = app_candidates[0]
            if _is_symlink(info):
                errors.append("runtime proof metadata ZIP entry must not be a symbolic link")
            if _is_symlink(app_info):
                errors.append("runtime proof unsigned app archive must not be a symbolic link")
            if info.file_size > max_metadata_bytes:
                errors.append(
                    "runtime proof metadata exceeds configured size limit: "
                    f"{info.file_size} > {max_metadata_bytes}"
                )
            if app_info.file_size > max_app_archive_bytes:
                errors.append(
                    "runtime proof unsigned app archive exceeds configured size limit: "
                    f"{app_info.file_size} > {max_app_archive_bytes}"
                )
            if errors:
                return errors

            with archive.open(info, "r") as source:
                payload = source.read(max_metadata_bytes + 1)
            if len(payload) > max_metadata_bytes:
                return [
                    "runtime proof metadata expanded beyond configured size limit: "
                    f"{len(payload)} > {max_metadata_bytes}"
                ]

            app_hasher = hashlib.sha256()
            app_bytes = 0
            with archive.open(app_info, "r") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    app_bytes += len(chunk)
                    if app_bytes > max_app_archive_bytes:
                        return [
                            "runtime proof unsigned app archive expanded beyond configured "
                            f"size limit: {app_bytes} > {max_app_archive_bytes}"
                        ]
                    app_hasher.update(chunk)
            app_digest = "sha256:" + app_hasher.hexdigest()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("xb") as handle:
                handle.write(payload)

            if app_archive_digest_output_path is not None:
                app_archive_digest_output_path.parent.mkdir(parents=True, exist_ok=True)
                with app_archive_digest_output_path.open("x", encoding="utf-8") as handle:
                    handle.write(app_digest + "\n")
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        return [f"invalid runtime proof artifact ZIP: {error}"]

    return []


__all__ = [
    "APP_ARCHIVE_NAME",
    "DEFAULT_MAX_METADATA_BYTES",
    "extract_runtime_proof_metadata",
]
