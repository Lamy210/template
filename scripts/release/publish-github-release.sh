#!/usr/bin/env bash
set -euo pipefail

: "${TAG_NAME:?TAG_NAME is required}"
: "${DMG_PATH:?DMG_PATH is required}"
: "${RELEASE_PROVENANCE_PATH:?RELEASE_PROVENANCE_PATH is required}"

checksum_path="${DMG_PATH}.sha256"
if [[ "$(basename "${RELEASE_PROVENANCE_PATH}")" != "release-provenance.json" ]]; then
  echo "Final release provenance must be named release-provenance.json." >&2
  exit 1
fi

assets=("${DMG_PATH}" "${checksum_path}" "${RELEASE_PROVENANCE_PATH}")
for file_path in "${assets[@]}"; do
  if [[ ! -f "${file_path}" || -L "${file_path}" ]]; then
    echo "Release asset must be a regular non-symlink file: ${file_path}" >&2
    exit 1
  fi
done

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to validate the release checksum." >&2
  exit 1
}

if ! checksum_digest="$(
  python3 "$(dirname "${BASH_SOURCE[0]}")/release_checksum.py" \
    "${checksum_path}" \
    "$(basename "${DMG_PATH}")"
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

release_state_args=(--metadata "${release_json}" --tag "${TAG_NAME}")
for asset_name in "${expected_asset_names[@]}"; do
  release_state_args+=(--asset "${asset_name}")
done
python3 "$(dirname "${BASH_SOURCE[0]}")/verify-release-state.py" "${release_state_args[@]}"

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
