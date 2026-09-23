#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/publish-release.XXXXXX")"
trap 'rm -rf "${TMP_ROOT}"' EXIT

LOCAL_DIR="${TMP_ROOT}/local"
REMOTE_DIR="${TMP_ROOT}/remote"
FAKE_BIN="${TMP_ROOT}/bin"
LOG_PATH="${TMP_ROOT}/gh.log"
DMG_PATH="${LOCAL_DIR}/ExampleApp-v1.2.3.dmg"
CHECKSUM_PATH="${DMG_PATH}.sha256"
RELEASE_PROVENANCE_PATH="${LOCAL_DIR}/release-provenance.json"
TAG_NAME="v1.2.3"

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
printf '%s\n' "$*" >>"${GH_FAKE_LOG}"

if [[ "$1" != "release" ]]; then
  echo "Unexpected gh command: $*" >&2
  exit 90
fi

case "$2" in
  view)
    [[ "${GH_FAKE_RELEASE_EXISTS:-false}" == "true" ]] || exit 1
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
    exit 0
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
    PATH="${FAKE_BIN}:${PATH}" \
    TAG_NAME="${TAG_NAME}" \
    DMG_PATH="${DMG_PATH}" \
    RELEASE_PROVENANCE_PATH="${RELEASE_PROVENANCE_PATH}" \
    bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

run_publisher_without_provenance() {
  GH_FAKE_LOG="${LOG_PATH}" \
    GH_FAKE_REMOTE_DIR="${REMOTE_DIR}" \
    PATH="${FAKE_BIN}:${PATH}" \
    TAG_NAME="${TAG_NAME}" \
    DMG_PATH="${DMG_PATH}" \
    bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

: >"${LOG_PATH}"
if GH_FAKE_RELEASE_EXISTS=false run_publisher_without_provenance; then
  echo "Publisher accepted a release without final provenance." >&2
  exit 1
fi
if [[ -s "${LOG_PATH}" ]]; then
  echo "Publisher contacted GitHub before rejecting missing final provenance." >&2
  exit 1
fi

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

: >"${LOG_PATH}"
GH_FAKE_RELEASE_EXISTS=false run_publisher
if ! grep -F "release create ${TAG_NAME}" "${LOG_PATH}" >/dev/null; then
  echo "New release was not created." >&2
  exit 1
fi
if grep -F -- "--clobber" "${LOG_PATH}" >/dev/null; then
  echo "Publisher must never use --clobber." >&2
  exit 1
fi
if ! grep -F "$(basename "${RELEASE_PROVENANCE_PATH}")" "${LOG_PATH}" >/dev/null; then
  echo "New release did not include release provenance." >&2
  exit 1
fi

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
