#!/usr/bin/env bash
set -euo pipefail

: "${DMG_PATH:?DMG_PATH is required}"
: "${APP_STORE_CONNECT_API_KEY_P8:?APP_STORE_CONNECT_API_KEY_P8 is required}"
: "${APP_STORE_CONNECT_KEY_ID:?APP_STORE_CONNECT_KEY_ID is required}"
: "${APP_STORE_CONNECT_ISSUER_ID:?APP_STORE_CONNECT_ISSUER_ID is required}"

if [[ ! -f "${DMG_PATH}" ]]; then
  echo "DMG not found: ${DMG_PATH}" >&2
  exit 1
fi

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
KEY_DIR="$(mktemp -d "${TEMP_ROOT%/}/notary-key.XXXXXX")"
KEY_PATH="${KEY_DIR}/AuthKey_${APP_STORE_CONNECT_KEY_ID}.p8"
RESULT_PATH="${TEMP_ROOT%/}/notary-result-${GITHUB_RUN_ID:-local}.json"
LOG_PATH="${TEMP_ROOT%/}/notary-log-${GITHUB_RUN_ID:-local}.json"

cleanup() {
  rm -rf "${KEY_DIR}"
}
trap cleanup EXIT

umask 077
printf '%s' "${APP_STORE_CONNECT_API_KEY_P8}" >"${KEY_PATH}"

xcrun notarytool submit "${DMG_PATH}" \
  --key "${KEY_PATH}" \
  --key-id "${APP_STORE_CONNECT_KEY_ID}" \
  --issuer "${APP_STORE_CONNECT_ISSUER_ID}" \
  --wait \
  --output-format json >"${RESULT_PATH}"

submission_id="$(python3 - "${RESULT_PATH}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle).get("id", ""))
PY
)"
status="$(python3 - "${RESULT_PATH}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle).get("status", ""))
PY
)"

printf 'Notarization submission: %s\n' "${submission_id:-unknown}"
printf 'Notarization status: %s\n' "${status:-unknown}"

if [[ -z "${submission_id}" ]]; then
  echo "Notarization response did not contain a submission ID." >&2
  cat "${RESULT_PATH}" >&2
  exit 1
fi

# Fetch the service log even on Accepted results so warnings remain available in
# the Actions log. On failure this is the primary diagnostic for signing issues.
if xcrun notarytool log "${submission_id}" \
  --key "${KEY_PATH}" \
  --key-id "${APP_STORE_CONNECT_KEY_ID}" \
  --issuer "${APP_STORE_CONNECT_ISSUER_ID}" \
  "${LOG_PATH}"; then
  cat "${LOG_PATH}"
else
  echo "Unable to retrieve notarization log for ${submission_id}." >&2
fi

if [[ "${status}" != "Accepted" ]]; then
  echo "Notarization failed with status: ${status:-unknown}" >&2
  exit 1
fi

xcrun stapler staple "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"
