#!/usr/bin/env bash
set -euo pipefail

: "${CASK_TOKEN:?CASK_TOKEN is required}"
: "${VERSION:?VERSION is required}"
: "${SHA256:?SHA256 is required}"
: "${GITHUB_OWNER:?GITHUB_OWNER is required}"
: "${GITHUB_REPO:?GITHUB_REPO is required}"
: "${DMG_BASENAME:?DMG_BASENAME is required}"
: "${APP_NAME:?APP_NAME is required}"
: "${DESCRIPTION:?DESCRIPTION is required}"
: "${HOMEPAGE:?HOMEPAGE is required}"
: "${BUNDLE_ID:?BUNDLE_ID is required}"
: "${OUTPUT_CASK:?OUTPUT_CASK is required}"
: "${CASK_OUTPUT_ROOT:?CASK_OUTPUT_ROOT is required}"

CASK_TEMPLATE_ROOT="${CASK_TEMPLATE_ROOT:-.}"
TEMPLATE_PATH="${CASK_TEMPLATE:-${CASK_TEMPLATE_ROOT}/templates/homebrew/Cask.rb.template}"

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  echo "Cask template not found: ${TEMPLATE_PATH}" >&2
  exit 1
fi

validate_output_path() {
  python3 "$(dirname "${BASH_SOURCE[0]}")/validate-cask-output-path.py" \
    --root "${CASK_OUTPUT_ROOT}" \
    --output "${OUTPUT_CASK}"
}

validate_output_path
mkdir -p "$(dirname "${OUTPUT_CASK}")"
validate_output_path

python3 - "${TEMPLATE_PATH}" "${OUTPUT_CASK}" "${CASK_OUTPUT_ROOT}" "${CASK_TEMPLATE_ROOT}" <<'PY'
import os
import pathlib
import re
import secrets
import stat
import sys

source = pathlib.Path(os.path.abspath(sys.argv[1]))
target = pathlib.Path(os.path.abspath(sys.argv[2]))
root = pathlib.Path(os.path.abspath(sys.argv[3]))
template_root = pathlib.Path(os.path.abspath(sys.argv[4]))

if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
    raise SystemExit("platform does not provide O_NOFOLLOW/O_DIRECTORY")

try:
    template_relative = source.relative_to(template_root)
except ValueError as error:
    raise SystemExit("Cask template escaped configured template root") from error
if template_relative == pathlib.Path(".") or template_relative.name in {"", ".", ".."}:
    raise SystemExit("Cask template must name a file below the configured template root")

max_template_bytes = 1024 * 1024
template_root_descriptor = None
template_parent_descriptor = None
source_descriptor = None
try:
    template_root_descriptor = os.open(
        template_root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )
    template_parent_descriptor = template_root_descriptor
    for part in template_relative.parent.parts:
        if part in {"", ".", ".."}:
            raise SystemExit("Cask template contains an invalid parent component")
        next_descriptor = os.open(
            part,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=template_parent_descriptor,
        )
        if template_parent_descriptor != template_root_descriptor:
            os.close(template_parent_descriptor)
        template_parent_descriptor = next_descriptor

    source_descriptor = os.open(
        template_relative.name,
        os.O_RDONLY | os.O_NOFOLLOW,
        dir_fd=template_parent_descriptor,
    )
    source_metadata = os.fstat(source_descriptor)
    if not stat.S_ISREG(source_metadata.st_mode):
        raise SystemExit("Cask template must be a regular file")
    if source_metadata.st_size > max_template_bytes:
        raise SystemExit(
            f"Cask template exceeds {max_template_bytes} byte limit"
        )
    with os.fdopen(source_descriptor, "rb", closefd=False) as source_handle:
        template_bytes = source_handle.read(max_template_bytes + 1)
    if len(template_bytes) > max_template_bytes:
        raise SystemExit(
            f"Cask template exceeds {max_template_bytes} byte limit while reading"
        )
    try:
        text = template_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit("Cask template must be valid UTF-8") from error
except OSError as error:
    raise SystemExit(
        f"unable to open Cask template below trusted root without following symlinks: {error}"
    ) from error
finally:
    if source_descriptor is not None:
        os.close(source_descriptor)
    if (
        template_parent_descriptor is not None
        and template_parent_descriptor != template_root_descriptor
    ):
        os.close(template_parent_descriptor)
    if template_root_descriptor is not None:
        os.close(template_root_descriptor)

keys = (
    "CASK_TOKEN",
    "VERSION",
    "SHA256",
    "GITHUB_OWNER",
    "GITHUB_REPO",
    "DMG_BASENAME",
    "APP_NAME",
    "DESCRIPTION",
    "HOMEPAGE",
    "BUNDLE_ID",
)


def ruby_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("#{", "\\#{")
    )


dmg_basename = os.environ["DMG_BASENAME"]
if re.fullmatch(
    r"[A-Za-z0-9._+-]*#\{version\}[A-Za-z0-9._+-]*\.dmg",
    dmg_basename,
) is None:
    raise SystemExit(
        "DMG_BASENAME must be a literal DMG basename with exactly one #{version} placeholder"
    )

for key in keys:
    value = os.environ[key]
    if key == "DMG_BASENAME":
        rendered = ruby_string(value).replace(r"\#{version}", "#{version}")
    else:
        rendered = ruby_string(value)
    text = text.replace("{{" + key + "}}", rendered)

if "{{" in text or "}}" in text:
    raise SystemExit("Unresolved placeholder remains in rendered Cask")

try:
    relative = target.relative_to(root)
except ValueError as error:
    raise SystemExit("Cask output escaped configured output root") from error
if relative == pathlib.Path(".") or relative.name in {"", ".", ".."}:
    raise SystemExit("Cask output must name a file below the configured output root")

parent_descriptor = os.open(
    root,
    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
)
temp_name = None
temp_descriptor = None
try:
    current_descriptor = parent_descriptor
    for part in relative.parent.parts:
        if part in {"", ".", ".."}:
            raise SystemExit("Cask output contains an invalid parent component")
        next_descriptor = os.open(
            part,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=current_descriptor,
        )
        if current_descriptor != parent_descriptor:
            os.close(current_descriptor)
        current_descriptor = next_descriptor

    if current_descriptor != parent_descriptor:
        os.close(parent_descriptor)
        parent_descriptor = current_descriptor

    try:
        existing = os.stat(
            relative.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode):
            raise SystemExit("Cask output became a symlink after validation")
        if not stat.S_ISREG(existing.st_mode):
            raise SystemExit("Existing Cask output must remain a regular file")

    for _ in range(32):
        candidate = f".{relative.name}.tmp.{secrets.token_hex(8)}"
        try:
            temp_descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o644,
                dir_fd=parent_descriptor,
            )
            temp_name = candidate
            break
        except FileExistsError:
            continue
    if temp_descriptor is None or temp_name is None:
        raise SystemExit("unable to allocate exclusive Cask staging file")

    with os.fdopen(
        temp_descriptor,
        "w",
        encoding="utf-8",
        closefd=False,
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(temp_descriptor)

    os.replace(
        temp_name,
        relative.name,
        src_dir_fd=parent_descriptor,
        dst_dir_fd=parent_descriptor,
    )
    temp_name = None
finally:
    if temp_descriptor is not None:
        os.close(temp_descriptor)
    if temp_name is not None:
        try:
            os.unlink(temp_name, dir_fd=parent_descriptor)
        except OSError:
            pass
    os.close(parent_descriptor)
PY

printf 'Rendered %s\n' "${OUTPUT_CASK}"
