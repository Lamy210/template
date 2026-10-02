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
SOURCE_SHA="1111111111111111111111111111111111111111"
PUBLISHER_SHA="2222222222222222222222222222222222222222"
EXPECTED_REPOSITORY_ID="123"

mkdir -p "${LOCAL_DIR}" "${REMOTE_DIR}" "${FAKE_BIN}"
printf 'stable-release-payload\n' >"${DMG_PATH}"
EXPECTED_DMG_PATH="${TMP_ROOT}/expected-release.dmg"
cp "${DMG_PATH}" "${EXPECTED_DMG_PATH}"
(
  cd "${LOCAL_DIR}"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)
printf '{"schemaVersion":1,"dmgSha256":"sha256:test"}\n' >"${RELEASE_PROVENANCE_PATH}"

cat >"${FAKE_BIN}/git" <<'FAKE_GIT'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "cat-file" && "${2:-}" == "-e" ]]; then
  exit 0
fi
if [[ "${1:-}" == "merge-base" && "${2:-}" == "--is-ancestor" ]]; then
  exit 0
fi

echo "Unexpected git command: $*" >&2
exit 97
FAKE_GIT
chmod 0755 "${FAKE_BIN}/git"

cat >"${FAKE_BIN}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail

: "${GH_FAKE_LOG:?GH_FAKE_LOG is required}"
: "${GH_FAKE_STATE_FILE:?GH_FAKE_STATE_FILE is required}"
printf '%s\n' "$*" >>"${GH_FAKE_LOG}"

if [[ "$1" == "api" ]]; then
  if [[ "$*" == "api repos/${GITHUB_REPOSITORY}" ]]; then
    if [[ "${GH_FAKE_MUTATE_LOCAL_AFTER_SNAPSHOT:-false}" == "true" &&
          ! -f "${GH_FAKE_STATE_FILE}" ]]; then
      : "${GH_FAKE_LOCAL_DMG_PATH:?GH_FAKE_LOCAL_DMG_PATH is required}"
      printf 'tampered-after-snapshot\n' >"${GH_FAKE_LOCAL_DMG_PATH}"
    fi
    repository_full_name="${GITHUB_REPOSITORY}"
    if [[ "${GH_FAKE_REPOSITORY_DRIFT_AFTER_CREATE:-false}" == "true" && -f "${GH_FAKE_STATE_FILE}" ]]; then
      repository_full_name="example/renamed-release-repo"
    fi
    printf '{"id":%s,"full_name":"%s"}\n' "${GH_FAKE_REPOSITORY_ID:-123}" "${repository_full_name}"
    exit 0
  fi

  if [[ " $* " == *" /repos/${GITHUB_REPOSITORY}/git/ref/tags/${TAG_NAME} "* ]]; then
    resolved_sha="${SOURCE_SHA:?SOURCE_SHA is required}"
    if [[ "${GH_FAKE_TAG_DRIFT_AFTER_CREATE:-false}" == "true" && -f "${GH_FAKE_STATE_FILE}" ]]; then
      resolved_sha="3333333333333333333333333333333333333333"
    fi
    printf '{"ref":"refs/tags/%s","object":{"type":"commit","sha":"%s"}}\n' "${TAG_NAME}" "${resolved_sha}"
    exit 0
  fi

  if [[ " $* " == *" repos/${GITHUB_REPOSITORY}/releases?per_page=100 "* ]]; then
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

  echo "Unexpected gh api command: $*" >&2
  exit 92
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
    if [[ " $* " == *" --json assets,isDraft,isImmutable,isPrerelease,tagName "* ]]; then
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
    "isImmutable": os.environ.get("GH_FAKE_IS_IMMUTABLE", "true") == "true",
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
  verify)
    if [[ "${3:-}" == "--help" ]]; then
      [[ "${GH_FAKE_ATTESTATION_COMMANDS_AVAILABLE:-true}" == "true" ]]
      exit
    fi
    if [[ "${GH_FAKE_RELEASE_ATTESTATION_VALID:-true}" != "true" ]]; then
      exit 95
    fi
    printf '{"verified":true}\n'
    ;;
  verify-asset)
    if [[ "${3:-}" == "--help" ]]; then
      [[ "${GH_FAKE_ATTESTATION_COMMANDS_AVAILABLE:-true}" == "true" ]]
      exit
    fi
    asset_name="$(basename "${4:-}")"
    if [[ -n "${GH_FAKE_INVALID_ASSET_ATTESTATION_NAME:-}" && "${asset_name}" == "${GH_FAKE_INVALID_ASSET_ATTESTATION_NAME}" ]]; then
      exit 96
    fi
    printf '{"verified":true}\n'
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
  local publisher_dmg_path="${DMG_PATH}"

  GH_FAKE_LOG="${LOG_PATH}" \
    GH_FAKE_REMOTE_DIR="${REMOTE_DIR}" \
    GH_FAKE_STATE_FILE="${STATE_FILE}" \
    GH_FAKE_CORRUPT_AFTER_CREATE="${GH_FAKE_CORRUPT_AFTER_CREATE:-false}" \
    GH_FAKE_CREATE_RACE="${GH_FAKE_CREATE_RACE:-false}" \
    GH_FAKE_CREATE_FAIL_EMPTY="${GH_FAKE_CREATE_FAIL_EMPTY:-false}" \
    GH_FAKE_RELEASE_LIST_FAIL="${GH_FAKE_RELEASE_LIST_FAIL:-false}" \
    GH_FAKE_RELEASE_LIST_FAIL_WHEN_STATE="${GH_FAKE_RELEASE_LIST_FAIL_WHEN_STATE:-false}" \
    GH_FAKE_TAG_DRIFT_AFTER_CREATE="${GH_FAKE_TAG_DRIFT_AFTER_CREATE:-false}" \
    GH_FAKE_IS_IMMUTABLE="${GH_FAKE_IS_IMMUTABLE:-true}" \
    GH_FAKE_RELEASE_ATTESTATION_VALID="${GH_FAKE_RELEASE_ATTESTATION_VALID:-true}" \
    GH_FAKE_ATTESTATION_COMMANDS_AVAILABLE="${GH_FAKE_ATTESTATION_COMMANDS_AVAILABLE:-true}" \
    GH_FAKE_INVALID_ASSET_ATTESTATION_NAME="${GH_FAKE_INVALID_ASSET_ATTESTATION_NAME:-}" \
    GH_FAKE_REPOSITORY_DRIFT_AFTER_CREATE="${GH_FAKE_REPOSITORY_DRIFT_AFTER_CREATE:-false}" \
    GH_FAKE_MUTATE_LOCAL_AFTER_SNAPSHOT="${GH_FAKE_MUTATE_LOCAL_AFTER_SNAPSHOT:-false}" \
    GH_FAKE_LOCAL_DMG_PATH="${publisher_dmg_path}" \
    GH_FAKE_REPOSITORY_ID="${GH_FAKE_REPOSITORY_ID:-123}" \
    PATH="${FAKE_BIN}:${PATH}" \
    GH_TOKEN="test-token" \
    TAG_NAME="${TAG_NAME}" \
    SOURCE_SHA="${SOURCE_SHA}" \
    PUBLISHER_SHA="${PUBLISHER_SHA}" \
    EXPECTED_REPOSITORY_ID="${EXPECTED_REPOSITORY_ID}" \
    GITHUB_REPOSITORY="${GITHUB_REPOSITORY}" \
    DMG_PATH="${publisher_dmg_path}" \
    RELEASE_PROVENANCE_PATH="${RELEASE_PROVENANCE_PATH}" \
    bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

run_publisher_without_repository() {
  GH_FAKE_LOG="${LOG_PATH}" \
    GH_FAKE_REMOTE_DIR="${REMOTE_DIR}" \
    GH_FAKE_STATE_FILE="${STATE_FILE}" \
    PATH="${FAKE_BIN}:${PATH}" \
    GH_TOKEN="test-token" \
    TAG_NAME="${TAG_NAME}" \
    SOURCE_SHA="${SOURCE_SHA}" \
    PUBLISHER_SHA="${PUBLISHER_SHA}" \
    EXPECTED_REPOSITORY_ID="${EXPECTED_REPOSITORY_ID}" \
    DMG_PATH="${DMG_PATH}" \
    RELEASE_PROVENANCE_PATH="${RELEASE_PROVENANCE_PATH}" \
    env -u GITHUB_REPOSITORY bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

run_publisher_without_provenance() {
  GH_FAKE_LOG="${LOG_PATH}" \
    GH_FAKE_REMOTE_DIR="${REMOTE_DIR}" \
    PATH="${FAKE_BIN}:${PATH}" \
    GH_TOKEN="test-token" \
    TAG_NAME="${TAG_NAME}" \
    SOURCE_SHA="${SOURCE_SHA}" \
    PUBLISHER_SHA="${PUBLISHER_SHA}" \
    EXPECTED_REPOSITORY_ID="${EXPECTED_REPOSITORY_ID}" \
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
if EXPECTED_REPOSITORY_ID=invalid GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Publisher accepted a malformed expected repository ID." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting a malformed repository ID." >&2
  exit 1
fi

: >"${LOG_PATH}"
if GH_FAKE_ATTESTATION_COMMANDS_AVAILABLE=false GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Publisher accepted a gh CLI without immutable release attestation commands." >&2
  exit 1
fi
if grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher mutated GitHub Release state before attestation CLI capability validation." >&2
  exit 1
fi
if grep -F "api repos/${GITHUB_REPOSITORY}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher contacted repository APIs before local attestation CLI capability validation." >&2
  exit 1
fi
if ! grep -F "release verify --help" "${LOG_PATH}" >/dev/null; then
  echo "Publisher did not preflight release attestation CLI support." >&2
  exit 1
fi

: >"${LOG_PATH}"
if EXPECTED_REPOSITORY_ID=999 GH_FAKE_RELEASE_EXISTS=false run_publisher; then
  echo "Publisher accepted a repository API ID mismatch." >&2
  exit 1
fi
if grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher reached release creation after repository ID mismatch." >&2
  exit 1
fi
if ! grep -F "api repos/${GITHUB_REPOSITORY}" "${LOG_PATH}" >/dev/null; then
  echo "Repository ID mismatch probe did not query canonical repository identity." >&2
  exit 1
fi

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

rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*
cp "${EXPECTED_DMG_PATH}" "${DMG_PATH}"
(
  cd "${LOCAL_DIR}"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)
: >"${LOG_PATH}"
GH_FAKE_RELEASE_EXISTS=false GH_FAKE_MUTATE_LOCAL_AFTER_SNAPSHOT=true run_publisher
grep -F "tampered-after-snapshot" "${DMG_PATH}" >/dev/null
cmp -s "${REMOTE_DIR}/$(basename "${DMG_PATH}")" "${EXPECTED_DMG_PATH}" || {
  echo "Publisher uploaded bytes from the mutable source path instead of the validated snapshot." >&2
  exit 1
}
if grep -F "release create ${TAG_NAME} ${DMG_PATH}" "${LOG_PATH}" >/dev/null; then
  echo "Publisher passed the mutable original DMG path to release creation." >&2
  exit 1
fi

rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*
cp "${EXPECTED_DMG_PATH}" "${DMG_PATH}"
(
  cd "${LOCAL_DIR}"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)

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
if ! grep -F "release view ${TAG_NAME} --repo ${GITHUB_REPOSITORY} --json assets,isDraft,isImmutable,isPrerelease,tagName" "${LOG_PATH}" >/dev/null; then
  echo "New release was not re-read for post-create state verification." >&2
  exit 1
fi
for asset_name in "$(basename "${DMG_PATH}")" "$(basename "${CHECKSUM_PATH}")" "$(basename "${RELEASE_PROVENANCE_PATH}")"; do
  if ! grep -F "release download ${TAG_NAME} --repo ${GITHUB_REPOSITORY} --pattern ${asset_name}" "${LOG_PATH}" >/dev/null; then
    echo "New release asset was not re-downloaded for post-create verification: ${asset_name}" >&2
    exit 1
  fi
done
if ! grep -F "release verify ${TAG_NAME} --repo ${GITHUB_REPOSITORY} --format json" "${LOG_PATH}" >/dev/null; then
  echo "New release attestation was not verified." >&2
  exit 1
fi
for asset_path in "${DMG_PATH}" "${CHECKSUM_PATH}" "${RELEASE_PROVENANCE_PATH}"; do
  asset_name="$(basename "${asset_path}")"
  if ! grep -F "release verify-asset ${TAG_NAME} " "${LOG_PATH}" |
    grep -F "/${asset_name} --repo ${GITHUB_REPOSITORY} --format json" >/dev/null; then
    echo "New release asset attestation was not verified from a snapshot: ${asset_name}" >&2
    exit 1
  fi
  if grep -F "release verify-asset ${TAG_NAME} ${asset_path} --repo" "${LOG_PATH}" >/dev/null; then
    echo "Publisher attestation verification reused mutable source path: ${asset_path}" >&2
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
if GH_FAKE_RELEASE_EXISTS=false GH_FAKE_TAG_DRIFT_AFTER_CREATE=true run_publisher; then
  echo "Publisher accepted a release after the source tag moved during publication." >&2
  exit 1
fi
if ! grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Tag-drift publication probe did not create a release first." >&2
  exit 1
fi
if [[ "$(grep -Fc "/git/ref/tags/${TAG_NAME}" "${LOG_PATH}")" -lt 2 ]]; then
  echo "Publisher did not rebind the release tag both before and after publication." >&2
  exit 1
fi
rm -f "${STATE_FILE}"
rm -f "${REMOTE_DIR}"/*
: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false GH_FAKE_REPOSITORY_DRIFT_AFTER_CREATE=true run_publisher; then
  echo "Publisher accepted a repository rename during publication." >&2
  exit 1
fi
if ! grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "Repository-drift publication probe did not create a release first." >&2
  exit 1
fi
if [[ "$(grep -Fc "api repos/${GITHUB_REPOSITORY}" "${LOG_PATH}")" -lt 2 ]]; then
  echo "Publisher did not rebind repository identity both before and after publication." >&2
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
if GH_FAKE_RELEASE_EXISTS=true GH_FAKE_RELEASE_ATTESTATION_VALID=false run_publisher; then
  echo "Existing immutable release without a valid signed attestation was incorrectly accepted." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Publisher mutated release state after signed release attestation failure." >&2
  exit 1
fi

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true GH_FAKE_INVALID_ASSET_ATTESTATION_NAME="$(basename "${DMG_PATH}")" run_publisher; then
  echo "Existing immutable release with an invalid asset attestation was incorrectly accepted." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Publisher mutated release state after asset attestation failure." >&2
  exit 1
fi

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=true GH_FAKE_IS_IMMUTABLE=false run_publisher; then
  echo "Mutable existing release was incorrectly accepted as a production no-op." >&2
  exit 1
fi
if grep -E '^release (create|upload) ' "${LOG_PATH}" >/dev/null; then
  echo "Mutable existing release was mutated instead of rejected." >&2
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
