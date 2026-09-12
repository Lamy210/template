#!/usr/bin/env bash
set -euo pipefail

: "${CERTIFICATE_P12_BASE64:?CERTIFICATE_P12_BASE64 is required}"
: "${CERTIFICATE_PASSWORD:?CERTIFICATE_PASSWORD is required}"

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
KEYCHAIN_PATH="${TEMP_ROOT}/macos-release-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}.keychain-db"
CERTIFICATE_PATH="${TEMP_ROOT}/developer-id-${GITHUB_RUN_ID:-local}.p12"
KEYCHAIN_PASSWORD="$(openssl rand -hex 32)"

cleanup_certificate() {
  rm -f "${CERTIFICATE_PATH}"
}
trap cleanup_certificate EXIT

# macOS base64 uses -D for decode.
printf '%s' "${CERTIFICATE_P12_BASE64}" | base64 -D >"${CERTIFICATE_PATH}"

security create-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"
security set-keychain-settings -lut 21600 "${KEYCHAIN_PATH}"
security unlock-keychain -p "${KEYCHAIN_PASSWORD}" "${KEYCHAIN_PATH}"
security import "${CERTIFICATE_PATH}" \
  -k "${KEYCHAIN_PATH}" \
  -P "${CERTIFICATE_PASSWORD}" \
  -T /usr/bin/codesign \
  -T /usr/bin/security

security set-key-partition-list \
  -S apple-tool:,apple: \
  -s \
  -k "${KEYCHAIN_PASSWORD}" \
  "${KEYCHAIN_PATH}" >/dev/null

# Restrict discovery to the temporary keychain on the ephemeral release runner.
security list-keychains -d user -s "${KEYCHAIN_PATH}"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'keychain-path=%s\n' "${KEYCHAIN_PATH}" >>"${GITHUB_OUTPUT}"
else
  printf '%s\n' "${KEYCHAIN_PATH}"
fi
