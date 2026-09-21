#!/usr/bin/env bash
set -euo pipefail

: "${TAG_NAME:?TAG_NAME is required}"
: "${DMG_PATH:?DMG_PATH is required}"

checksum_path="${DMG_PATH}.sha256"
for file_path in "${DMG_PATH}" "${checksum_path}"; do
  if [[ ! -f "${file_path}" ]]; then
    echo "Release asset not found: ${file_path}" >&2
    exit 1
  fi
done

if ! gh release view "${TAG_NAME}" >/dev/null 2>&1; then
  gh release create "${TAG_NAME}" \
    "${DMG_PATH}" \
    "${checksum_path}" \
    --verify-tag \
    --generate-notes \
    --title "${TAG_NAME}"
  exit 0
fi

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to verify immutable release asset membership." >&2
  exit 1
}

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
download_dir="$(mktemp -d "${TEMP_ROOT%/}/existing-release.XXXXXX")"
cleanup() {
  rm -rf "${download_dir}"
}
trap cleanup EXIT

release_json="${download_dir}/release.json"
if ! gh release view "${TAG_NAME}" --json assets >"${release_json}"; then
  echo "Failed to inspect existing release assets for ${TAG_NAME}." >&2
  exit 1
fi

python3 - "${release_json}" "$(basename "${DMG_PATH}")" "$(basename "${checksum_path}")" <<'PY'
import json
from collections import Counter
import sys

release_path, *expected_names = sys.argv[1:]
try:
    with open(release_path, encoding="utf-8") as handle:
        release = json.load(handle)
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"Existing release metadata is unreadable: {error}")

if not isinstance(release, dict):
    raise SystemExit("Existing release metadata must be a JSON object")
assets = release.get("assets")
if not isinstance(assets, list):
    raise SystemExit("Existing release assets metadata must be an array")

actual_names = []
for asset in assets:
    if not isinstance(asset, dict):
        raise SystemExit("Existing release asset metadata must contain only objects")
    name = asset.get("name")
    if not isinstance(name, str) or not name:
        raise SystemExit("Existing release asset name must be a non-empty string")
    actual_names.append(name)

actual = Counter(actual_names)
expected = Counter(expected_names)
if actual != expected:
    missing = sorted((expected - actual).elements())
    unexpected = sorted((actual - expected).elements())
    details = []
    if missing:
        details.append(f"missing={missing!r}")
    if unexpected:
        details.append(f"unexpected={unexpected!r}")
    raise SystemExit(
        "Existing release asset set does not exactly match immutable publication contract"
        + (f": {', '.join(details)}" if details else "")
    )
PY

for local_path in "${DMG_PATH}" "${checksum_path}"; do
  asset_name="$(basename "${local_path}")"
  if ! gh release download "${TAG_NAME}" \
    --pattern "${asset_name}" \
    --dir "${download_dir}"; then
    echo "Existing release ${TAG_NAME} is missing required asset: ${asset_name}" >&2
    exit 1
  fi

  remote_path="${download_dir}/${asset_name}"
  if [[ ! -f "${remote_path}" ]]; then
    echo "Downloaded release asset not found: ${remote_path}" >&2
    exit 1
  fi

  local_digest="$(shasum -a 256 "${local_path}" | awk '{print $1}')"
  remote_digest="$(shasum -a 256 "${remote_path}" | awk '{print $1}')"
  if [[ "${local_digest}" != "${remote_digest}" ]]; then
    echo "Refusing to replace immutable release asset ${asset_name} for ${TAG_NAME}." >&2
    exit 1
  fi
done

printf 'GitHub Release %s already contains identical assets; publication is a no-op.\n' "${TAG_NAME}"
