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

cleanup() {
  rm -rf "${KEY_DIR}"
}
trap cleanup EXIT

umask 077
printf '%s' "${APP_STORE_CONNECT_API_KEY_P8}" > "${KEY_PATH}"

xcrun notarytool submit "${DMG_PATH}" \
  --key "${KEY_PATH}" \
  --key-id "${APP_STORE_CONNECT_KEY_ID}" \
  --issuer "${APP_STORE_CONNECT_ISSUER_ID}" \
  --wait \
  --output-format json > "${RESULT_PATH}"

python3 - "${RESULT_PATH}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    result = json.load(handle)

status = result.get("status")
submission_id = result.get("id", "unknown")
print(f"Notarization submission: {submission_id}")
print(f"Notarization status: {status}")
if status != "Accepted":
    raise SystemExit(f"Notarization failed with status: {status}")
PY

xcrun stapler staple "${DMG_PATH}"
xcrun stapler validate "${DMG_PATH}"
