#!/usr/bin/env bash
set -euo pipefail

: "${ARCHIVE_PATH:?ARCHIVE_PATH is required}"
: "${OUTPUT_DIR:?OUTPUT_DIR is required}"
: "${APP_BASENAME:?APP_BASENAME is required}"

if [[ ! -f "${ARCHIVE_PATH}" ]]; then
  echo "Application archive not found: ${ARCHIVE_PATH}" >&2
  exit 1
fi

if [[ "${APP_BASENAME}" != *.app || "${APP_BASENAME}" == */* || "${APP_BASENAME}" == "." || "${APP_BASENAME}" == ".." ]]; then
  echo "APP_BASENAME must be a .app basename." >&2
  exit 1
fi

members_file="$(mktemp "${TMPDIR:-/tmp}/app-artifact-members.XXXXXX")"
trap 'rm -f "${members_file}"' EXIT

tar -tzf "${ARCHIVE_PATH}" >"${members_file}"
if [[ ! -s "${members_file}" ]]; then
  echo "Application archive is empty." >&2
  exit 1
fi

while IFS= read -r member; do
  if [[ -z "${member}" || "${member}" == /* ]]; then
    echo "Unsafe archive member path: ${member}" >&2
    exit 1
  fi

  IFS='/' read -r -a components <<<"${member}"
  if [[ "${components[0]}" != "${APP_BASENAME}" ]]; then
    echo "Archive member is outside expected app bundle: ${member}" >&2
    exit 1
  fi
  for component in "${components[@]}"; do
    if [[ "${component}" == ".." ]]; then
      echo "Archive member contains path traversal: ${member}" >&2
      exit 1
    fi
  done
done <"${members_file}"

python3 - "${ARCHIVE_PATH}" "${APP_BASENAME}" <<'PY'
import posixpath
import sys
import tarfile

archive_path, app_basename = sys.argv[1:]
app_prefix = f"{app_basename}/"


def is_inside_app(path: str) -> bool:
    return path == app_basename or path.startswith(app_prefix)


with tarfile.open(archive_path, "r:gz") as archive:
    seen_paths: set[str] = set()

    for member in archive.getmembers():
        canonical_name = posixpath.normpath(member.name)
        if canonical_name in seen_paths:
            raise SystemExit(f"Duplicate archive member path: {canonical_name}")
        seen_paths.add(canonical_name)

        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise SystemExit(f"Unsupported archive member type: {member.name}")

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
