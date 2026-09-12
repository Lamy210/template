#!/usr/bin/env bash
set -euo pipefail

: "${APP_PATH:?APP_PATH is required}"
: "${SIGNING_IDENTITY:?SIGNING_IDENTITY is required}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Application bundle not found: ${APP_PATH}" >&2
  exit 1
fi

codesign_args=(
  --force
  --options runtime
  --timestamp
  --sign "${SIGNING_IDENTITY}"
)

if [[ -n "${KEYCHAIN_PATH:-}" ]]; then
  codesign_args+=(--keychain "${KEYCHAIN_PATH}")
fi

if [[ -n "${ENTITLEMENTS_PATH:-}" ]]; then
  if [[ ! -f "${ENTITLEMENTS_PATH}" ]]; then
    echo "Entitlements file not found: ${ENTITLEMENTS_PATH}" >&2
    exit 1
  fi
  codesign_args+=(--entitlements "${ENTITLEMENTS_PATH}")
fi

# Intentionally do not use --deep for signing. Applications containing nested
# frameworks, helpers, XPC services, extensions, or other code should provide a
# project-specific inside-out signing adapter before this root bundle step.
codesign "${codesign_args[@]}" "${APP_PATH}"

codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
codesign --display --verbose=4 "${APP_PATH}"
