#!/usr/bin/env bash
set -euo pipefail

: "${APP_PATH:?APP_PATH is required}"
: "${DMG_PATH:?DMG_PATH is required}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Application bundle not found: ${APP_PATH}" >&2
  exit 1
fi

if [[ ! -f "${DMG_PATH}" ]]; then
  echo "DMG not found: ${DMG_PATH}" >&2
  exit 1
fi

codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
spctl --assess --type execute --verbose=4 "${APP_PATH}"
codesign --verify --verbose=2 "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"
hdiutil verify "${DMG_PATH}"

CHECKSUM_PATH="${DMG_PATH}.sha256"
(
  cd "$(dirname "${DMG_PATH}")"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)

cat "${CHECKSUM_PATH}"
