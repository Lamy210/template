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

rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"
tar -xzf "${ARCHIVE_PATH}" -C "${OUTPUT_DIR}"

app_path="${OUTPUT_DIR}/${APP_BASENAME}"
if [[ ! -d "${app_path}" || -L "${app_path}" ]]; then
  echo "Expected application bundle was not extracted safely: ${app_path}" >&2
  exit 1
fi
