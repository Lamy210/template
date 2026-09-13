#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/app-artifact-handoff.XXXXXX")"
trap 'rm -rf "${TMP_ROOT}"' EXIT

APP_PATH="${TMP_ROOT}/build/TestApp.app"
EXECUTABLE_PATH="${APP_PATH}/Contents/MacOS/TestApp"
ARCHIVE_PATH="${TMP_ROOT}/artifact/unsigned-macos-app.tar.gz"
EXTRACT_ROOT="${TMP_ROOT}/downloaded"

mkdir -p "$(dirname "${EXECUTABLE_PATH}")" "$(dirname "${ARCHIVE_PATH}")"
printf '#!/usr/bin/env bash\nexit 0\n' >"${EXECUTABLE_PATH}"
chmod 0755 "${EXECUTABLE_PATH}"

if [[ ! -x "${EXECUTABLE_PATH}" ]]; then
  echo "Fixture executable is not executable before packaging." >&2
  exit 1
fi

APP_PATH="${APP_PATH}" \
  OUTPUT_ARCHIVE="${ARCHIVE_PATH}" \
  bash "${ROOT_DIR}/scripts/release/package-app-artifact.sh"

# GitHub Actions Artifact does not need the archive file itself to be executable.
# Simulate the downloaded file mode being normalized while requiring the tar
# payload to retain the app bundle's executable mode.
chmod 0644 "${ARCHIVE_PATH}"

ARCHIVE_PATH="${ARCHIVE_PATH}" \
  OUTPUT_DIR="${EXTRACT_ROOT}" \
  APP_BASENAME="TestApp.app" \
  bash "${ROOT_DIR}/scripts/release/extract-app-artifact.sh"

RESTORED_EXECUTABLE="${EXTRACT_ROOT}/TestApp.app/Contents/MacOS/TestApp"
if [[ ! -f "${RESTORED_EXECUTABLE}" ]]; then
  echo "Restored bundle executable is missing: ${RESTORED_EXECUTABLE}" >&2
  exit 1
fi
if [[ ! -x "${RESTORED_EXECUTABLE}" ]]; then
  echo "Restored bundle executable lost its executable bit." >&2
  exit 1
fi

printf 'App artifact handoff preserved executable permissions.\n'
