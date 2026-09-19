from __future__ import annotations

import os
from pathlib import Path
import posixpath
import re
import stat
import zipfile


EXPECTED_RELEASE_FILES = frozenset(
    {
        "release-input/unsigned-macos-app.tar.gz",
        "release-input/build-provenance.json",
    }
)
DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:[/\\]")


def _unix_file_type(info: zipfile.ZipInfo) -> int:
    if info.create_system != 3:
        return 0
    return (info.external_attr >> 16) & stat.S_IFMT(0o170000)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return _unix_file_type(info) == stat.S_IFLNK


def _validate_member_name(name: str) -> tuple[str | None, str | None]:
    if not name:
        return None, "ZIP member name must not be empty"
    if name.startswith(("/", "\\")):
        return None, f"absolute ZIP member path is forbidden: {name}"
    if DRIVE_PREFIX_RE.match(name):
        return None, f"drive-prefixed ZIP member path is forbidden: {name}"
    if "\\" in name:
        return None, f"backslash ZIP member path is forbidden: {name}"

    components = name.split("/")
    if any(component == ".." for component in components):
        return None, f"ZIP member path traversal is forbidden: {name}"

    canonical = posixpath.normpath(name)
    if canonical in {"", ".", ".."}:
        return None, f"invalid canonical ZIP member path: {name}"
    if canonical != "release-input" and not canonical.startswith("release-input/"):
        return None, f"ZIP member is outside release-input: {name}"
    return canonical, None


def validate_and_extract_release_artifact(
    archive_path: Path,
    output_dir: Path,
) -> list[str]:
    errors: list[str] = []
    if not archive_path.is_file():
        return [f"artifact ZIP not found: {archive_path}"]
    if output_dir.exists():
        return [f"output directory must not already exist: {output_dir}"]

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if not infos:
                return ["artifact ZIP is empty"]

            seen: set[str] = set()
            file_infos: dict[str, zipfile.ZipInfo] = {}
            for info in infos:
                canonical, name_error = _validate_member_name(info.filename)
                if name_error is not None:
                    errors.append(name_error)
                    continue
                assert canonical is not None

                if canonical in seen:
                    errors.append(f"duplicate canonical ZIP member path: {canonical}")
                    continue
                seen.add(canonical)

                if _is_symlink(info):
                    errors.append(f"symlink ZIP member is forbidden: {info.filename}")
                    continue

                file_type = _unix_file_type(info)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    errors.append(f"unsupported ZIP member type: {info.filename}")
                    continue

                if info.is_dir():
                    continue
                file_infos[canonical] = info

            file_paths = set(file_infos)
            missing = sorted(EXPECTED_RELEASE_FILES - file_paths)
            unexpected = sorted(file_paths - EXPECTED_RELEASE_FILES)
            if missing:
                errors.append(f"missing files in release artifact: {missing!r}")
            if unexpected:
                errors.append(f"unexpected files in release artifact: {unexpected!r}")

            if errors:
                return errors

            output_dir.mkdir(parents=True, exist_ok=False)
            for canonical in sorted(EXPECTED_RELEASE_FILES):
                info = file_infos[canonical]
                destination = output_dir.joinpath(*canonical.split("/"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, destination.open("xb") as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                os.chmod(destination, 0o600)
    except (zipfile.BadZipFile, OSError, RuntimeError) as error:
        return [f"invalid ZIP artifact: {error}"]

    return []
