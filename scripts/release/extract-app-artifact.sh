#!/usr/bin/env bash
set -euo pipefail

: "${ARCHIVE_PATH:?ARCHIVE_PATH is required}"
: "${OUTPUT_DIR:?OUTPUT_DIR is required}"
: "${APP_BASENAME:?APP_BASENAME is required}"

MAX_APP_ARCHIVE_MEMBERS="${MAX_APP_ARCHIVE_MEMBERS:-100000}"
MAX_APP_EXTRACTED_BYTES="${MAX_APP_EXTRACTED_BYTES:-8589934592}"

if [[ ! -f "${ARCHIVE_PATH}" ]]; then
  echo "Application archive not found: ${ARCHIVE_PATH}" >&2
  exit 1
fi

if [[ "${APP_BASENAME}" != *.app || "${APP_BASENAME}" == */* || "${APP_BASENAME}" == "." || "${APP_BASENAME}" == ".." ]]; then
  echo "APP_BASENAME must be a .app basename." >&2
  exit 1
fi

if [[ ! "${MAX_APP_ARCHIVE_MEMBERS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "MAX_APP_ARCHIVE_MEMBERS must be a positive integer." >&2
  exit 1
fi
if [[ ! "${MAX_APP_EXTRACTED_BYTES}" =~ ^[1-9][0-9]*$ ]]; then
  echo "MAX_APP_EXTRACTED_BYTES must be a positive integer." >&2
  exit 1
fi

python3 - "${ARCHIVE_PATH}" "${APP_BASENAME}" "${MAX_APP_ARCHIVE_MEMBERS}" "${MAX_APP_EXTRACTED_BYTES}" <<'PY'
import posixpath
import sys
import tarfile

archive_path, app_basename, max_members_text, max_bytes_text = sys.argv[1:]
app_prefix = f"{app_basename}/"
max_members = int(max_members_text)
max_bytes = int(max_bytes_text)


def is_inside_app(path: str) -> bool:
    return path == app_basename or path.startswith(app_prefix)


with tarfile.open(archive_path, "r:gz") as archive:
    seen_paths: set[str] = set()
    member_count = 0
    total_file_bytes = 0

    for member in archive:
        member_count += 1
        if member_count > max_members:
            raise SystemExit(
                "Application archive member count exceeds configured limit: "
                f"{member_count} > {max_members}"
            )

        if not member.name or member.name.startswith("/"):
            raise SystemExit(f"Unsafe archive member path: {member.name}")

        components = member.name.split("/")
        if any(component == ".." for component in components):
            raise SystemExit(f"Archive member contains path traversal: {member.name}")

        canonical_name = posixpath.normpath(member.name)
        if not is_inside_app(canonical_name):
            raise SystemExit(
                f"Archive member is outside expected app bundle: {member.name}"
            )

        if canonical_name in seen_paths:
            raise SystemExit(f"Duplicate archive member path: {canonical_name}")
        seen_paths.add(canonical_name)

        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise SystemExit(f"Unsupported archive member type: {member.name}")

        if member.isfile():
            if member.size < 0:
                raise SystemExit(f"Archive member has invalid size: {member.name}")
            total_file_bytes += member.size
            if total_file_bytes > max_bytes:
                raise SystemExit(
                    "Application archive extracted file size exceeds configured limit: "
                    f"{total_file_bytes} > {max_bytes}"
                )

        if member.issym():
            target = member.linkname
            if not target or target.startswith("/"):
                raise SystemExit(
                    f"Unsafe archive symlink target: {member.name} -> {target}"
                )

            resolved_target = posixpath.normpath(
                posixpath.join(posixpath.dirname(member.name), target)
            )
            if not is_inside_app(resolved_target):
                raise SystemExit(
                    f"Archive symlink escapes expected app bundle: {member.name} -> {target}"
                )

        if member.islnk():
            target = member.linkname
            if not target or target.startswith("/"):
                raise SystemExit(
                    f"Unsafe archive hard link target: {member.name} -> {target}"
                )

            resolved_target = posixpath.normpath(target)
            if not is_inside_app(resolved_target):
                raise SystemExit(
                    f"Archive hard link escapes expected app bundle: {member.name} -> {target}"
                )
PY

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"
tar -xzf "${ARCHIVE_PATH}" -C "${OUTPUT_DIR}"

app_path="${OUTPUT_DIR}/${APP_BASENAME}"
if [[ ! -d "${app_path}" || -L "${app_path}" ]]; then
  echo "Expected application bundle was not extracted safely: ${app_path}" >&2
  exit 1
fi
