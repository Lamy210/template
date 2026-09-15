#!/usr/bin/env bash
set -euo pipefail

: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
result_bundle="${RUNNER_TEMP}/e2e.xcresult"
attachments="${RUNNER_TEMP}/e2e-attachments"

if [[ ! -d "${result_bundle}" ]]; then
  echo "No E2E result bundle exists; attachment export skipped."
  exit 0
fi

[[ ! -e "${attachments}" ]] || {
  echo "E2E attachment output already exists." >&2
  exit 2
}
mkdir -p "${attachments}"

xcrun xcresulttool export attachments \
  --path "${result_bundle}" \
  --output-path "${attachments}"
