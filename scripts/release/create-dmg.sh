#!/usr/bin/env bash
set -euo pipefail

: "${APP_PATH:?APP_PATH is required}"
: "${APP_NAME:?APP_NAME is required}"
: "${OUTPUT_DMG:?OUTPUT_DMG is required}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Application bundle not found: ${APP_PATH}" >&2
  exit 1
fi

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
STAGING_DIR="$(mktemp -d "${TEMP_ROOT%/}/dmg-stage.XXXXXX")"

cleanup() {
  rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

mkdir -p "$(dirname "${OUTPUT_DMG}")"
ditto "${APP_PATH}" "${STAGING_DIR}/${APP_NAME}.app"
ln -s /Applications "${STAGING_DIR}/Applications"

rm -f "${OUTPUT_DMG}"
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${STAGING_DIR}" \
  -format UDZO \
  -ov \
  "${OUTPUT_DMG}"

hdiutil verify "${OUTPUT_DMG}"
