#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/publish-release.XXXXXX")"
trap 'rm -rf "${TMP_ROOT}"' EXIT

LOCAL_DIR="${TMP_ROOT}/local"
REMOTE_DIR="${TMP_ROOT}/remote"
FAKE_BIN="${TMP_ROOT}/bin"
LOG_PATH="${TMP_ROOT}/gh.log"
STATE_FILE="${TMP_ROOT}/release-created"
DMG_PATH="${LOCAL_DIR}/ExampleApp-v1.2.3.dmg"
CHECKSUM_PATH="${DMG_PATH}.sha256"
RELEASE_PROVENANCE_PATH="${LOCAL_DIR}/release-provenance.json"
TAG_NAME="v1.2.3"
GITHUB_REPOSITORY="example/release-repo"

mkdir -p "${LOCAL_DIR}" "${REMOTE_DIR}" "${FAKE_BIN}"
printf 'stable-release-payload\n' >"${DMG_PATH}"
(
  cd "${LOCAL_DIR}"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)
printf '{"schemaVersion":1,"dmgSha256":"sha256:test"}\n' >"${RELEASE_PROVENANCE_PATH}"

cat >"${FAKE_BIN}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail

: "${GH_FAKE_LOG:?GH_FAKE_LOG is required}"
: "${GH_FAKE_STATE_FILE:?GH_FAKE_STATE_FILE is required}"
printf '%s\n' "$*" >>"${GH_FAKE_LOG}"

if [[ "$1" == "api" ]]; then
  if [[ "${GH_FAKE_RELEASE_LIST_FAIL:-false}" == "true" ]]; then
    exit 1
  fi
  if [[ "${GH_FAKE_RELEASE_LIST_FAIL_WHEN_STATE:-false}" == "true" && -f "${GH_FAKE_STATE_FILE}" ]]; then
    exit 1
  fi
  if [[ "${GH_FAKE_RELEASE_EXISTS:-false}" == "true" || -f "${GH_FAKE_STATE_FILE}" ]]; then
    printf '%s\n' "${TAG_NAME:?TAG_NAME is required}"
  fi
  exit 0
fi

if [[ "$1" != "release" ]]; then
  echo "Unexpected gh command: $*" >&2
  exit 90
fi

case "$2" in
  view)
    if [[ "${GH_FAKE_RELEASE_EXISTS:-false}" != "true" && ! -f "${GH_FAKE_STATE_FILE}" ]]; then
      exit 1
    fi
    if [[ " $* " == *" --json assets,isDraft,isPrerelease,tagName "* ]]; then
      : "${GH_FAKE_REMOTE_DIR:?GH_FAKE_REMOTE_DIR is required}"
      python3 - "${GH_FAKE_REMOTE_DIR}" <<'PY'
import json
import os
from pathlib import Path
import sys

remote_dir = Path(sys.argv[1])
assets = [{"name": path.name} for path in sorted(remote_dir.iterdir()) if path.is_file()]
payload = {
    "assets": assets,
    "isDraft": os.environ.get("GH_FAKE_IS_DRAFT", "false") == "true",
    "isPrerelease": os.environ.get("GH_FAKE_IS_PRERELEASE", "false") == "true",
    "tagName": os.environ.get("GH_FAKE_TAG_NAME", "v1.2.3"),
}
print(json.dumps(payload, separators=(",", ":")))
PY
    fi
    ;;
  create)
    : "${GH_FAKE_REMOTE_DIR:?GH_FAKE_REMOTE_DIR is required}"
    shift 3
    for argument in "$@"; do
      if [[ -f "${argument}" ]]; then
        cp "${argument}" "${GH_FAKE_REMOTE_DIR}/$(basename "${argument}")"
      fi
    done
    if [[ "${GH_FAKE_CORRUPT_AFTER_CREATE:-false}" == "true" ]]; then
      for dmg in "${GH_FAKE_REMOTE_DIR}"/*.dmg; do
        if [[ -f "${dmg}" ]]; then
          printf 'corrupted-after-create\n' >"${dmg}"
          break
        fi
      done
    fi
    : >"${GH_FAKE_STATE_FILE}"
    if [[ "${GH_FAKE_CREATE_FAIL_EMPTY:-false}" == "true" ]]; then
      rm -f "${GH_FAKE_STATE_FILE}"
      rm -f "${GH_FAKE_REMOTE_DIR}"/*
      exit 1
    fi
    if [[ "${GH_FAKE_CREATE_RACE:-false}" == "true" ]]; then
      exit 1
    fi
    ;;
  download)
    : "${GH_FAKE_REMOTE_DIR:?GH_FAKE_REMOTE_DIR is required}"
    pattern=""
    output_dir=""
    shift 3
    while (($# > 0)); do
      case "$1" in
        --pattern)
          pattern="$2"
          shift 2
          ;;
        --dir)
          output_dir="$2"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    if [[ -z "${pattern}" || -z "${output_dir}" || ! -f "${GH_FAKE_REMOTE_DIR}/${pattern}" ]]; then
      exit 1
    fi
    mkdir -p "${output_dir}"
    cp "${GH_FAKE_REMOTE_DIR}/${pattern}" "${output_dir}/${pattern}"
    ;;
  *)
    echo "Unexpected gh release command: $*" >&2
    exit 91
    ;;
esac
FAKE_GH
chmod 0755 "${FAKE_BIN}/gh"

run_publisher() {
  GH_FAKE_LOG="${LOG_PATH}" \
    GH_FAKE_REMOTE_DIR="${REMOTE_DIR}" \
    GH_FAKE_STATE_FILE="${STATE_FILE}" \
    GH_FAKE_CORRUPT_AFTER_CREATE="${GH_FAKE_CORRUPT_AFTER_CREATE:-false}" \
    GH_FAKE_CREATE_RACE="${GH_FAKE_CREATE_RACE:-false}" \
    GH_FAKE_CREATE_FAIL_EMPTY="${GH_FAKE_CREATE_FAIL_EMPTY:-false}" \
    GH_FAKE_RELEASE_LIST_FAIL="${GH_FAKE_RELEASE_LIST_FAIL:-false}" \
    GH_FAKE_RELEASE_LIST_FAIL_WHEN_STATE="${GH_FAKE_RELEASE_LIST_FAIL_WHEN_STATE:-false}" \
    PATH="${FAKE_BIN}:${PATH}" \
    TAG_NAME="${TAG_NAME}" \
    GITHUB_REPOSITORY="${GITHUB_REPOSITORY}" \
    DMG_PATH="${DMG_PATH}" \
    RELEASE_PROVENANCE_PATH="${RELEASE_PROVENANCE_PATH}" \
    bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

run_publisher_without_repository() {
  GH_FAKE_LOG="${LOG_PATH}" \
    GH_FAKE_REMOTE_DIR="${REMOTE_DIR}" \
    GH_FAKE_STATE_FILE="${STATE_FILE}" \
    PATH="${FAKE_BIN}:${PATH}" \
    TAG_NAME="${TAG_NAME}" \
    DMG_PATH="${DMG_PATH}" \
    RELEASE_PROVENANCE_PATH="${RELEASE_PROVENANCE_PATH}" \
    env -u GITHUB_REPOSITORY bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

run_publisher_without_provenance() {
  GH_FAKE_LOG="${LOG_PATH}" \
    GH_FAKE_REMOTE_DIR="${REMOTE_DIR}" \
    PATH="${FAKE_BIN}:${PATH}" \
    TAG_NAME="${TAG_NAME}" \
    GITHUB_REPOSITORY="${GITHUB_REPOSITORY}" \
    DMG_PATH="${DMG_PATH}" \
    bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher_without_repository; then
  echo "Publisher accepted a release without explicit repository identity." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting missing repository identity." >&2
  exit 1
fi

original_repository="${GITHUB_REPOSITORY}"
GITHUB_REPOSITORY="../escape"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Publisher accepted an unsafe repository identity." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting unsafe repository identity." >&2
  exit 1
fi
GITHUB_REPOSITORY="${original_repository}"

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher_without_provenance; then
  echo "Publisher accepted a release without final provenance." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting missing final provenance." >&2
  exit 1
fi

original_tag_name="${TAG_NAME}"
for invalid_tag in "v01.2.3" "--help"; do
  TAG_NAME="${invalid_tag}"
  : >"${LOG_PATH}"
  if GH_FAKE_RELEASE_EXISTS=false run_publisher; then
    echo "Publisher accepted invalid stable release tag: ${invalid_tag}" >&2
    exit 1
  fi
  if [[ -s "${LOG_PATH}" ]]; then
    echo "Publisher contacted GitHub before rejecting invalid stable release tag: ${invalid_tag}" >&2
    exit 1
  fi
done
TAG_NAME="${original_tag_name}"

original_dmg_path="${DMG_PATH}"
unsafe_dmg_path="${LOCAL_DIR}/unsafe[asset].dmg"
cp "${original_dmg_path}" "${unsafe_dmg_path}"
(
  cd "${LOCAL_DIR}"
  shasum -a 256 "$(basename "${unsafe_dmg_path}")" >"$(basename "${unsafe_dmg_path}").sha256"
)
DMG_PATH="${unsafe_dmg_path}"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Publisher accepted unsafe DMG asset basename." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting unsafe DMG asset basename." >&2
  exit 1
fi
DMG_PATH="${original_dmg_path}"
rm -f "${unsafe_dmg_path}" "${unsafe_dmg_path}.sha256"

original_provenance_path="${RELEASE_PROVENANCE_PATH}"
wrong_provenance_path="${LOCAL_DIR}/provenance.json"
cp "${original_provenance_path}" "${wrong_provenance_path}"
RELEASE_PROVENANCE_PATH="${wrong_provenance_path}"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Publisher accepted a non-canonical provenance asset name." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting a non-canonical provenance asset name." >&2
  exit 1
fi
RELEASE_PROVENANCE_PATH="${original_provenance_path}"
rm -f "${wrong_provenance_path}"

real_provenance_path="${LOCAL_DIR}/release-provenance.real.json"
mv "${RELEASE_PROVENANCE_PATH}" "${real_provenance_path}"
ln -s "$(basename "${real_provenance_path}")" "${RELEASE_PROVENANCE_PATH}"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Publisher accepted a symlinked final provenance asset." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting a symlinked provenance asset." >&2
  exit 1
fi
rm -f "${RELEASE_PROVENANCE_PATH}"
mv "${real_provenance_path}" "${RELEASE_PROVENANCE_PATH}"

rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false GH_FAKE_RELEASE_LIST_FAIL=true run_publisher; then
  echo "Publisher treated a release-list API failure as release absence." >&2
  exit 1
fi
if grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher attempted release creation after release-list API failure." >&2
  exit 1
fi
if ! grep -F "api --paginate repos/${GITHUB_REPOSITORY}/releases?per_page=100 --jq .[].tag_name" "${LOG_PATH}" >/dev/null; then
  echo "Publisher did not use the paginated explicit-repository release probe." >&2
  exit 1
fi

: >"${LOG_PATH}"
GH_FAKE_RELEASE_EXISTS=false run_publisher
if ! grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "New release was not created." >&2
  exit 1
fi
if ! grep -F -- "--repo ${GITHUB_REPOSITORY}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher did not bind GitHub Release operations to the explicit repository." >&2
  exit 1
fi
if ! grep -F "release view ${TAG_NAME} --repo ${GITHUB_REPOSITORY} --json assets,isDraft,isPrerelease,tagName" "${LOG_PATH}" >/dev/null; then
  echo "New release was not re-read for post-create state verification." >&2
  exit 1
fi
for asset_name in "$(basename "${DMG_PATH}")" "$(basename "${CHECKSUM_PATH}")" "$(basename "${RELEASE_PROVENANCE_PATH}")"; do
  if ! grep -F "release download ${TAG_NAME} --repo ${GITHUB_REPOSITORY} --pattern ${asset_name}" "${LOG_PATH}" >/dev/null; then
    echo "New release asset was not re-downloaded for post-create verification: ${asset_name}" >&2
    exit 1
  fi
done
if grep -F -- "--clobber" "${LOG_PATH}" >/dev/null; then
  echo "Publisher must never use --clobber." >&2
  exit 1
fi
if ! grep -F "$(basename "${RELEASE_PROVENANCE_PATH}")" "${LOG_PATH}" >/dev/null; then
  echo "New release did not include release provenance." >&2
  exit 1
fi

rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false GH_FAKE_CORRUPT_AFTER_CREATE=true run_publisher; then
  echo "Publisher accepted a newly-created release whose remote DMG bytes drifted." >&2
  exit 1
fi
if ! grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Post-create corruption probe did not create a release first." >&2
  exit 1
fi
if ! grep -F "release download ${TAG_NAME} --repo ${GITHUB_REPOSITORY} --pattern $(basename "${DMG_PATH}")" "${LOG_PATH}" >/dev/null; then
  echo "Post-create corruption probe did not re-download the created DMG." >&2
  exit 1
fi
rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*

: >"${LOG_PATH}"
GH_FAKE_RELEASE_EXISTS=false GH_FAKE_CREATE_RACE=true run_publisher
if ! grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Concurrent-create probe did not attempt release creation." >&2
  exit 1
fi
if [[ "$(grep -Fc "api --paginate repos/${GITHUB_REPOSITORY}/releases?per_page=100 --jq .[].tag_name" "${LOG_PATH}")" -lt 2 ]]; then
  echo "Publisher did not re-probe release existence after a concurrent create race." >&2
  exit 1
fi
for asset_name in "$(basename "${DMG_PATH}")" "$(basename "${CHECKSUM_PATH}")" "$(basename "${RELEASE_PROVENANCE_PATH}")"; do
  if ! grep -F "release download ${TAG_NAME} --repo ${GITHUB_REPOSITORY} --pattern ${asset_name}" "${LOG_PATH}" >/dev/null; then
    echo "Concurrent-create path did not verify remote asset: ${asset_name}" >&2
    exit 1
  fi
done

rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false GH_FAKE_CREATE_FAIL_EMPTY=true run_publisher; then
  echo "Publisher accepted a failed create with no concurrent release to verify." >&2
  exit 1
fi
if [[ "$(grep -Fc "api --paginate repos/${GITHUB_REPOSITORY}/releases?per_page=100 --jq .[].tag_name" "${LOG_PATH}")" -lt 2 ]]; then
  echo "Publisher did not re-check remote existence after failed creation." >&2
  exit 1
fi
if grep -F "release download ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher downloaded assets even though no concurrent release existed." >&2
  exit 1
fi

rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false GH_FAKE_CREATE_RACE=true GH_FAKE_RELEASE_LIST_FAIL_WHEN_STATE=true run_publisher; then
  echo "Publisher accepted a concurrent-create path whose release state could not be re-queried." >&2
  exit 1
fi
if grep -F "release download ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher downloaded assets after concurrent release-state lookup failure." >&2
  exit 1
fi

rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*

printf '%064d  %s\n' 0 "$(basename "${DMG_PATH}")" >"${CHECKSUM_PATH}"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Mismatched local checksum was incorrectly accepted for publication." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Publisher reached GitHub mutation with a mismatched local checksum." >&2
  exit 1
fi
printf 'not-a-canonical-checksum\n' >"${CHECKSUM_PATH}"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Malformed local checksum was incorrectly accepted for publication." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Publisher reached GitHub mutation with a malformed local checksum." >&2
  exit 1
fi

(
  cd "${LOCAL_DIR}"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)

cp "${DMG_PATH}" "${REMOTE_DIR}/$(basename "${DMG_PATH}")"
cp "${CHECKSUM_PATH}" "${REMOTE_DIR}/$(basename "${CHECKSUM_PATH}")"
cp "${RELEASE_PROVENANCE_PATH}" "${REMOTE_DIR}/$(basename "${RELEASE_PROVENANCE_PATH}")"
: >"${LOG_PATH}"
GH_FAKE_RELEASE_EXISTS=true run_publisher
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Identical existing release was unexpectedly mutated." >&2
  exit 1
fi
if grep -F -- "--clobber" "${LOG_PATH}" >/dev/null; then
  echo "Publisher must never use --clobber." >&2
  exit 1
fi

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true GH_FAKE_IS_DRAFT=true run_publisher; then
  echo "Draft existing release was incorrectly accepted as an immutable no-op." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Draft existing release was mutated instead of rejected." >&2
  exit 1
fi

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true GH_FAKE_IS_PRERELEASE=true run_publisher; then
  echo "Prerelease existing release was incorrectly accepted as a stable no-op." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Prerelease existing release was mutated instead of rejected." >&2
  exit 1
fi

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true GH_FAKE_TAG_NAME=v1.2.4 run_publisher; then
  echo "Existing release with mismatched tag identity was incorrectly accepted." >&2
  exit 1
fi

printf 'unexpected-release-asset\n' >"${REMOTE_DIR}/unexpected-debug-symbols.zip"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true run_publisher; then
  echo "Existing release with an unexpected extra asset was incorrectly accepted." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Existing release with an unexpected extra asset was mutated instead of rejected." >&2
  exit 1
fi
rm -f "${REMOTE_DIR}/unexpected-debug-symbols.zip"

printf 'different-release-payload\n' >"${REMOTE_DIR}/$(basename "${DMG_PATH}")"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true run_publisher; then
  echo "Changed existing release asset was incorrectly accepted." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Changed existing release was mutated instead of rejected." >&2
  exit 1
fi

rm -f "${REMOTE_DIR}/$(basename "${CHECKSUM_PATH}")"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true run_publisher; then
  echo "Existing release with missing checksum asset was incorrectly accepted." >&2
  exit 1
fi

cp "${CHECKSUM_PATH}" "${REMOTE_DIR}/$(basename "${CHECKSUM_PATH}")"
rm -f "${REMOTE_DIR}/$(basename "${RELEASE_PROVENANCE_PATH}")"
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true run_publisher; then
  echo "Existing release with missing provenance asset was incorrectly accepted." >&2
  exit 1
fi

printf 'GitHub Release publication is immutable and idempotent for identical assets.\n'
