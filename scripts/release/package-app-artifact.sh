#!/usr/bin/env bash
set -euo pipefail

: "${APP_PATH:?APP_PATH is required}"
: "${OUTPUT_ARCHIVE:?OUTPUT_ARCHIVE is required}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Application bundle not found: ${APP_PATH}" >&2
  exit 1
fi

app_basename="$(basename "${APP_PATH}")"
if [[ "${app_basename}" != *.app || "${app_basename}" == */* ]]; then
  echo "APP_PATH must point to a .app bundle." >&2
  exit 1
fi

if [[ "${OUTPUT_ARCHIVE}" != *.tar.gz ]]; then
  echo "OUTPUT_ARCHIVE must end in .tar.gz." >&2
  exit 1
fi

archive_parent="$(dirname "${OUTPUT_ARCHIVE}")"
mkdir -p "${archive_parent}"
rm -f "${OUTPUT_ARCHIVE}"

tar -czf "${OUTPUT_ARCHIVE}" \
  -C "$(dirname "${APP_PATH}")" \
  "${app_basename}"

if [[ ! -f "${OUTPUT_ARCHIVE}" ]]; then
  echo "Failed to create application archive: ${OUTPUT_ARCHIVE}" >&2
  exit 1
fi
