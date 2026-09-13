#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/create-dmg-inputs.XXXXXX")"
trap 'rm -rf "${TMP_ROOT}"' EXIT

APP_PATH="${TMP_ROOT}/Example.app"
mkdir -p "${APP_PATH}"

assert_unsafe_app_name_rejected() {
  local app_name="$1"
  local output

  if output="$(
    APP_PATH="${APP_PATH}" \
      APP_NAME="${app_name}" \
      OUTPUT_DMG="${TMP_ROOT}/output.dmg" \
      bash "${ROOT_DIR}/scripts/release/create-dmg.sh" 2>&1
  )"; then
    echo "Unsafe APP_NAME was incorrectly accepted: ${app_name}" >&2
    exit 1
  fi

  if [[ "${output}" != *"APP_NAME must be an application basename without .app"* ]]; then
    echo "Unsafe APP_NAME did not fail at input validation: ${app_name}" >&2
    printf '%s\n' "${output}" >&2
    exit 1
  fi
}

assert_unsafe_app_name_rejected '../escape'
assert_unsafe_app_name_rejected 'nested/Example'
assert_unsafe_app_name_rejected 'Example.app'
assert_unsafe_app_name_rejected '.'
assert_unsafe_app_name_rejected '..'

printf 'DMG application-name validation rejects path-like or suffixed names.\n'
