from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from scripts.release.atomic_directory_publish import (
    AtomicDirectoryPublishError,
    atomic_publish_directory_noreplace,
)
from scripts.release.release_asset_limits import (
    MAX_RELEASE_DMG_BYTES,
    MAX_RELEASE_METADATA_BYTES,
    MAX_VERIFIED_RELEASE_ARTIFACT_ZIP_BYTES,
    release_asset_size_limit,
)
from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    snapshot_regular_file,
)


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_DMG_BYTES = MAX_RELEASE_DMG_BYTES
MAX_METADATA_BYTES = MAX_RELEASE_METADATA_BYTES


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _unix_file_type(info: zipfile.ZipInfo) -> int:
    if info.create_system != 3:
        return 0
    return (info.external_attr >> 16) & stat.S_IFMT(0o170000)


def _member_limit(name: str, dmg_name: str) -> int:
    limit = release_asset_size_limit(name, dmg_name=dmg_name)
    if limit is None:
        raise ValueError(f"unsupported verified release asset role: {name}")
    return limit


def validate_and_extract_verified_release_artifact(
    archive_path: Path,
    output_dir: Path,
    *,
    dmg_name: str,
    expected_digest: str,
) -> list[str]:
    if (
        not isinstance(dmg_name, str)
        or not dmg_name
        or Path(dmg_name).name != dmg_name
        or "/" in dmg_name
        or "\\" in dmg_name
    ):
        return ["verified release DMG name must be a literal basename"]
    if not isinstance(expected_digest, str) or DIGEST_RE.fullmatch(expected_digest) is None:
        return ["verified release artifact digest must use sha256:<64 lowercase hex>"]
    if output_dir.exists() or output_dir.is_symlink():
        return [f"output directory must not already exist or be a symlink: {output_dir}"]

    expected_names = {
        dmg_name,
        f"{dmg_name}.sha256",
        "release-provenance.json",
    }
    max_zip_bytes = MAX_VERIFIED_RELEASE_ARTIFACT_ZIP_BYTES

    try:
        with snapshot_regular_file(
            archive_path,
            prefix="verified-release-artifact.",
            max_bytes=max_zip_bytes,
        ) as snapshot_path:
            actual_digest = _sha256_file(snapshot_path)
            if actual_digest != expected_digest:
                return [
                    "verified release Artifact ZIP digest mismatch: "
                    f"expected {expected_digest}, got {actual_digest}"
                ]

            try:
                with zipfile.ZipFile(snapshot_path, "r") as archive:
                    infos = archive.infolist()
                    if len(infos) != len(expected_names):
                        return [
                            "verified release Artifact ZIP must contain exactly "
                            f"{len(expected_names)} file entries"
                        ]

                    file_infos: dict[str, zipfile.ZipInfo] = {}
                    errors: list[str] = []
                    for info in infos:
                        name = info.filename
                        if name not in expected_names:
                            errors.append(
                                f"unexpected verified release Artifact member: {name}"
                            )
                            continue
                        if name in file_infos:
                            errors.append(
                                f"duplicate verified release Artifact member: {name}"
                            )
                            continue
                        if info.is_dir():
                            errors.append(
                                f"verified release Artifact member must be a file: {name}"
                            )
                            continue

                        file_type = _unix_file_type(info)
                        if file_type == stat.S_IFLNK:
                            errors.append(
                                f"symlink verified release Artifact member is forbidden: {name}"
                            )
                            continue
                        if file_type not in {0, stat.S_IFREG}:
                            errors.append(
                                f"unsupported verified release Artifact member type: {name}"
                            )
                            continue

                        limit = _member_limit(name, dmg_name)
                        if info.file_size > limit:
                            errors.append(
                                "verified release Artifact member exceeds size limit: "
                                f"{name}: {info.file_size} > {limit}"
                            )
                            continue
                        file_infos[name] = info

                    missing = sorted(expected_names - set(file_infos))
                    if missing:
                        errors.append(
                            f"verified release Artifact is missing members: {missing!r}"
                        )
                    if errors:
                        return errors

                    output_dir.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(
                        prefix=f".{output_dir.name}.",
                        dir=output_dir.parent,
                    ) as temporary_directory:
                        stage = Path(temporary_directory) / "payload"
                        stage.mkdir(mode=0o700)

                        for name in sorted(expected_names):
                            info = file_infos[name]
                            destination = stage / name
                            limit = _member_limit(name, dmg_name)
                            copied = 0
                            with archive.open(info, "r") as source:
                                with destination.open("xb") as target:
                                    while True:
                                        chunk = source.read(1024 * 1024)
                                        if not chunk:
                                            break
                                        copied += len(chunk)
                                        if copied > limit:
                                            return [
                                                "verified release Artifact member grew beyond "
                                                f"size limit while extracting: {name}"
                                            ]
                                        target.write(chunk)
                            os.chmod(destination, 0o600)

                        if output_dir.exists() or output_dir.is_symlink():
                            return [
                                "output directory appeared during verified release extraction: "
                                f"{output_dir}"
                            ]
                        try:
                            atomic_publish_directory_noreplace(stage, output_dir)
                        except AtomicDirectoryPublishError as error:
                            return [
                                "unable to publish verified release output atomically: "
                                f"{error}"
                            ]
            except (zipfile.BadZipFile, OSError, RuntimeError) as error:
                return [f"invalid verified release Artifact ZIP: {error}"]
    except RegularFileSnapshotError as error:
        return [f"unable to snapshot verified release Artifact ZIP: {error}"]

    return []
