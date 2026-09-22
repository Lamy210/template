#!/usr/bin/env bash
set -euo pipefail

: "${TAG_NAME:?TAG_NAME is required}"
: "${DMG_PATH:?DMG_PATH is required}"

checksum_path="${DMG_PATH}.sha256"
assets=("${DMG_PATH}" "${checksum_path}")
if [[ -n "${RELEASE_PROVENANCE_PATH:-}" ]]; then
  assets+=("${RELEASE_PROVENANCE_PATH}")
fi

for file_path in "${assets[@]}"; do
  if [[ ! -f "${file_path}" ]]; then
    echo "Release asset not found: ${file_path}" >&2
    exit 1
  fi
done

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to validate the release checksum." >&2
  exit 1
}

if ! checksum_digest="$(
  python3 "$(dirname "${BASH_SOURCE[0]}")/../homebrew/parse_release_checksum.py"     "${checksum_path}"     "$(basename "${DMG_PATH}")"
)"; then
  echo "Release checksum asset failed canonical validation." >&2
  exit 1
fi

dmg_digest="$(shasum -a 256 "${DMG_PATH}" | awk '{print $1}')"
if [[ "${checksum_digest}" != "${dmg_digest}" ]]; then
  echo "Release checksum does not match DMG payload: ${DMG_PATH}" >&2
  exit 1
fi

if ! gh release view "${TAG_NAME}" >/dev/null 2>&1; then
  gh release create "${TAG_NAME}" \
    "${assets[@]}" \
    --verify-tag \
    --generate-notes \
    --title "${TAG_NAME}"
  exit 0
fi

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
download_dir="$(mktemp -d "${TEMP_ROOT%/}/existing-release.XXXXXX")"
cleanup() {
  rm -rf "${download_dir}"
}
trap cleanup EXIT

release_json="${download_dir}/release.json"
if ! gh release view "${TAG_NAME}" --json assets,isDraft,isPrerelease,tagName >"${release_json}"; then
  echo "Failed to inspect existing release metadata for ${TAG_NAME}." >&2
  exit 1
fi

expected_asset_names=()
for local_path in "${assets[@]}"; do
  expected_asset_names+=("$(basename "${local_path}")")
done

python3 - "${release_json}" "${TAG_NAME}" "${expected_asset_names[@]}" <<'PY'
import json
from collections import Counter
import sys

release_path, expected_tag, *expected_names = sys.argv[1:]
try:
    with open(release_path, encoding="utf-8") as handle:
        release = json.load(handle)
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"Existing release metadata is unreadable: {error}")

if not isinstance(release, dict):
    raise SystemExit("Existing release metadata must be a JSON object")

tag_name = release.get("tagName")
if not isinstance(tag_name, str) or tag_name != expected_tag:
    raise SystemExit(
        f"Existing release tag identity mismatch: expected {expected_tag!r}, got {tag_name!r}"
    )
if release.get("isDraft") is not False:
    raise SystemExit("Existing release must be published, not draft")
if release.get("isPrerelease") is not False:
    raise SystemExit("Existing release must be a stable release, not prerelease")

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

for local_path in "${assets[@]}"; do
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
