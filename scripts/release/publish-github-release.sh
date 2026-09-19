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
