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
TAG_NAME="v1.2.3"

mkdir -p "${LOCAL_DIR}" "${REMOTE_DIR}" "${FAKE_BIN}"
printf 'stable-release-payload\n' >"${DMG_PATH}"
(
  cd "${LOCAL_DIR}"
  shasum -a 256 "$(basename "${DMG_PATH}")" >"$(basename "${CHECKSUM_PATH}")"
)

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
    if [[ " $* " == *" --json assets "* ]]; then
      : "${GH_FAKE_REMOTE_DIR:?GH_FAKE_REMOTE_DIR is required}"
      python3 - "${GH_FAKE_REMOTE_DIR}" <<'PY'
import json
from pathlib import Path
import sys

remote_dir = Path(sys.argv[1])
assets = [{"name": path.name} for path in sorted(remote_dir.iterdir()) if path.is_file()]
print(json.dumps({"assets": assets}, separators=(",", ":")))
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
    bash "${ROOT_DIR}/scripts/release/publish-github-release.sh"
}

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

cp "${DMG_PATH}" "${REMOTE_DIR}/$(basename "${DMG_PATH}")"
cp "${CHECKSUM_PATH}" "${REMOTE_DIR}/$(basename "${CHECKSUM_PATH}")"
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

printf 'GitHub Release publication is immutable and idempotent for identical assets.\n'
