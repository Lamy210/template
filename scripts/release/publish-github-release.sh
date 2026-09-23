#!/usr/bin/env bash
set -euo pipefail

: "${TAG_NAME:?TAG_NAME is required}"
: "${DMG_PATH:?DMG_PATH is required}"
: "${RELEASE_PROVENANCE_PATH:?RELEASE_PROVENANCE_PATH is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

if [[ ! "${GITHUB_REPOSITORY}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "GITHUB_REPOSITORY must be in owner/repo form." >&2
  exit 1
fi
repository_owner="${GITHUB_REPOSITORY%%/*}"
repository_name="${GITHUB_REPOSITORY#*/}"
if [[ "${repository_owner}" == "." || "${repository_owner}" == ".." || "${repository_name}" == "." || "${repository_name}" == ".." ]]; then
  echo "GITHUB_REPOSITORY contains an invalid owner or repository component." >&2
  exit 1
fi

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
  echo "python3 is required to validate release publication inputs." >&2
  exit 1
}

dmg_name="$(basename "${DMG_PATH}")"
if ! python3 "$(dirname "${BASH_SOURCE[0]}")/validate-release-output-name.py" \
  --dmg-name "${dmg_name}"; then
  echo "Release DMG asset name failed pre-publication validation." >&2
  exit 1
fi

expected_asset_names=(
  "${dmg_name}"
  "${dmg_name}.sha256"
  "release-provenance.json"
)
release_expectation_args=(--tag "${TAG_NAME}")
for asset_name in "${expected_asset_names[@]}"; do
  release_expectation_args+=(--asset "${asset_name}")
done
if ! python3 "$(dirname "${BASH_SOURCE[0]}")/validate-release-expectations.py" \
  "${release_expectation_args[@]}"; then
  echo "Release tag or immutable asset identity failed pre-publication validation." >&2
  exit 1
fi

if ! checksum_digest="$(
  python3 "$(dirname "${BASH_SOURCE[0]}")/release_checksum.py" \
    "${checksum_path}" \
    "${dmg_name}"
)"; then
  echo "Release checksum asset failed canonical validation." >&2
  exit 1
fi

dmg_digest="$(shasum -a 256 "${DMG_PATH}" | awk '{print $1}')"
if [[ "${checksum_digest}" != "${dmg_digest}" ]]; then
  echo "Release checksum does not match DMG payload: ${DMG_PATH}" >&2
  exit 1
fi

release_exists() {
  local release_tags
  if ! release_tags="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/releases?per_page=100" --jq '.[].tag_name')"; then
    echo "Failed to enumerate GitHub Releases for ${GITHUB_REPOSITORY}." >&2
    return 2
  fi
  if grep -Fxq -- "${TAG_NAME}" <<<"${release_tags}"; then
    return 0
  fi
  return 1
}

release_created=false
release_lookup_status=0
release_exists || release_lookup_status=$?
case "${release_lookup_status}" in
  0)
    ;;
  1)
    if gh release create "${TAG_NAME}" \
      "${assets[@]}" \
      --repo "${GITHUB_REPOSITORY}" \
      --verify-tag \
      --generate-notes \
      --title "${TAG_NAME}"; then
      release_created=true
    else
      echo "GitHub Release creation did not succeed; checking for a concurrent immutable publication." >&2
      concurrent_lookup_status=0
      release_exists || concurrent_lookup_status=$?
      case "${concurrent_lookup_status}" in
        0)
          ;;
        1)
          echo "GitHub Release creation failed and no concurrent release is available for verification: ${TAG_NAME}" >&2
          exit 1
          ;;
        *)
          echo "GitHub Release creation failed and concurrent release state could not be verified: ${TAG_NAME}" >&2
          exit 1
          ;;
      esac
    fi
    ;;
  *)
    echo "Refusing to create a release because existing release state could not be verified." >&2
    exit 1
    ;;
esac

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
download_dir="$(mktemp -d "${TEMP_ROOT%/}/existing-release.XXXXXX")"
cleanup() {
  rm -rf "${download_dir}"
}
trap cleanup EXIT

release_json="${download_dir}/release.json"
if ! gh release view "${TAG_NAME}" \
  --repo "${GITHUB_REPOSITORY}" \
  --json assets,isDraft,isPrerelease,tagName >"${release_json}"; then
  echo "Failed to inspect existing release metadata for ${TAG_NAME}." >&2
  exit 1
fi

release_state_args=(--metadata "${release_json}" --tag "${TAG_NAME}")
for asset_name in "${expected_asset_names[@]}"; do
  release_state_args+=(--asset "${asset_name}")
done
python3 "$(dirname "${BASH_SOURCE[0]}")/verify-release-state.py" "${release_state_args[@]}"

for local_path in "${assets[@]}"; do
  asset_name="$(basename "${local_path}")"
  if ! gh release download "${TAG_NAME}" \
    --repo "${GITHUB_REPOSITORY}" \
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

if [[ "${release_created}" == true ]]; then
  printf 'GitHub Release %s was created and verified with identical remote assets.\n' "${TAG_NAME}"
else
  printf 'GitHub Release %s already contains identical assets; publication is a no-op.\n' "${TAG_NAME}"
fi
