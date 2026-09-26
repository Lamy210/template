#!/usr/bin/env bash
set -euo pipefail

: "${APP_PATH:?APP_PATH is required}"
: "${DMG_PATH:?DMG_PATH is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Application bundle not found: ${APP_PATH}" >&2
  exit 1
fi

if [[ ! -f "${DMG_PATH}" ]]; then
  echo "DMG not found: ${DMG_PATH}" >&2
  exit 1
fi

plist="${APP_PATH}/Contents/Info.plist"
executable_name="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "${plist}")"
APP_PATH="${APP_PATH}" \
  EXECUTABLE_NAME="${executable_name}" \
  bash "${SCRIPT_DIR}/verify-app-executable.sh"

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
MOUNT_POINT="$(mktemp -d "${TEMP_ROOT%/}/release-mount.XXXXXX")"
APP_BASENAME="$(basename "${APP_PATH}")"
MOUNTED=false

cleanup() {
  if [[ "${MOUNTED}" == true ]]; then
    hdiutil detach "${MOUNT_POINT}" -quiet || true
  fi
  rm -rf "${MOUNT_POINT}"
}
trap cleanup EXIT

# Validate both the signed application and the actual outer distribution file.
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
spctl --assess --type execute --verbose=4 "${APP_PATH}"
codesign --verify --verbose=2 "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"
hdiutil verify "${DMG_PATH}"
spctl --assess \
  --type open \
  --context context:primary-signature \
  --verbose=4 \
  "${DMG_PATH}"

# Mount the exact DMG that will be published and verify its payload is present,
# executable, and still has a valid code signature after packaging.
hdiutil attach \
  -readonly \
  -nobrowse \
  -mountpoint "${MOUNT_POINT}" \
  "${DMG_PATH}" >/dev/null
MOUNTED=true

mounted_app="${MOUNT_POINT}/${APP_BASENAME}"
if [[ ! -d "${mounted_app}" ]]; then
  echo "Expected application not found in DMG: ${APP_BASENAME}" >&2
  exit 1
fi

APP_PATH="${mounted_app}" \
  EXECUTABLE_NAME="${executable_name}" \
  bash "${SCRIPT_DIR}/verify-app-executable.sh"
codesign --verify --deep --strict --verbose=2 "${mounted_app}"

CHECKSUM_PATH="${DMG_PATH}.sha256"
(
  cd "$(dirname "${DMG_PATH}")"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)

cat "${CHECKSUM_PATH}"
