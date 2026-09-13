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

RESTORED_APP="${EXTRACT_ROOT}/TestApp.app"
RESTORED_EXECUTABLE="${RESTORED_APP}/Contents/MacOS/TestApp"
if [[ ! -f "${RESTORED_EXECUTABLE}" ]]; then
  echo "Restored bundle executable is missing: ${RESTORED_EXECUTABLE}" >&2
  exit 1
fi
if [[ ! -x "${RESTORED_EXECUTABLE}" ]]; then
  echo "Restored bundle executable lost its executable bit." >&2
  exit 1
fi

APP_PATH="${RESTORED_APP}" \
  EXECUTABLE_NAME="TestApp" \
  bash "${ROOT_DIR}/scripts/release/verify-app-executable.sh"

chmod 0644 "${RESTORED_EXECUTABLE}"
if APP_PATH="${RESTORED_APP}" \
  EXECUTABLE_NAME="TestApp" \
  bash "${ROOT_DIR}/scripts/release/verify-app-executable.sh"; then
  echo "Non-executable bundle binary was incorrectly accepted." >&2
  exit 1
fi
chmod 0755 "${RESTORED_EXECUTABLE}"

rm -f "${RESTORED_EXECUTABLE}"
ln -s /bin/sh "${RESTORED_EXECUTABLE}"
if APP_PATH="${RESTORED_APP}" \
  EXECUTABLE_NAME="TestApp" \
  bash "${ROOT_DIR}/scripts/release/verify-app-executable.sh"; then
  echo "Symlinked bundle executable was incorrectly accepted." >&2
  exit 1
fi
rm -f "${RESTORED_EXECUTABLE}"
printf '#!/usr/bin/env bash\nexit 0\n' >"${RESTORED_EXECUTABLE}"
chmod 0755 "${RESTORED_EXECUTABLE}"

UNSAFE_ARCHIVE="${TMP_ROOT}/artifact/unsafe-symlink.tar.gz"
UNSAFE_EXTRACT_ROOT="${TMP_ROOT}/unsafe-downloaded"
python3 - "${UNSAFE_ARCHIVE}" <<'PY'
import sys
import tarfile

archive_path = sys.argv[1]
with tarfile.open(archive_path, "w:gz") as archive:
    for name in (
        "TestApp.app",
        "TestApp.app/Contents",
        "TestApp.app/Contents/Resources",
    ):
        entry = tarfile.TarInfo(name)
        entry.type = tarfile.DIRTYPE
        entry.mode = 0o755
        archive.addfile(entry)

    link = tarfile.TarInfo("TestApp.app/Contents/Resources/escape")
    link.type = tarfile.SYMTYPE
    link.linkname = "../../../outside"
    archive.addfile(link)
PY

if ARCHIVE_PATH="${UNSAFE_ARCHIVE}" \
  OUTPUT_DIR="${UNSAFE_EXTRACT_ROOT}" \
  APP_BASENAME="TestApp.app" \
  bash "${ROOT_DIR}/scripts/release/extract-app-artifact.sh"; then
  echo "Archive with an escaping symlink target was incorrectly accepted." >&2
  exit 1
fi

UNSAFE_HARDLINK_ARCHIVE="${TMP_ROOT}/artifact/unsafe-hardlink.tar.gz"
python3 - "${UNSAFE_HARDLINK_ARCHIVE}" <<'PY'
import sys
import tarfile

archive_path = sys.argv[1]
with tarfile.open(archive_path, "w:gz") as archive:
    for name in (
        "TestApp.app",
        "TestApp.app/Contents",
        "TestApp.app/Contents/Resources",
    ):
        entry = tarfile.TarInfo(name)
        entry.type = tarfile.DIRTYPE
        entry.mode = 0o755
        archive.addfile(entry)

    link = tarfile.TarInfo("TestApp.app/Contents/Resources/escape-hardlink")
    link.type = tarfile.LNKTYPE
    link.linkname = "../../outside"
    archive.addfile(link)
PY

if hardlink_output="$(
  ARCHIVE_PATH="${UNSAFE_HARDLINK_ARCHIVE}" \
    OUTPUT_DIR="${TMP_ROOT}/unsafe-hardlink-downloaded" \
    APP_BASENAME="TestApp.app" \
    bash "${ROOT_DIR}/scripts/release/extract-app-artifact.sh" 2>&1
)"; then
  echo "Archive with an escaping hard-link target was incorrectly accepted." >&2
  exit 1
fi
if [[ "${hardlink_output}" != *"Archive hard link escapes expected app bundle"* ]]; then
  echo "Escaping hard link was not rejected during archive prevalidation." >&2
  printf '%s\n' "${hardlink_output}" >&2
  exit 1
fi

UNSAFE_FIFO_ARCHIVE="${TMP_ROOT}/artifact/unsafe-fifo.tar.gz"
python3 - "${UNSAFE_FIFO_ARCHIVE}" <<'PY'
import sys
import tarfile

archive_path = sys.argv[1]
with tarfile.open(archive_path, "w:gz") as archive:
    for name in (
        "TestApp.app",
        "TestApp.app/Contents",
        "TestApp.app/Contents/Resources",
    ):
        entry = tarfile.TarInfo(name)
        entry.type = tarfile.DIRTYPE
        entry.mode = 0o755
        archive.addfile(entry)

    fifo = tarfile.TarInfo("TestApp.app/Contents/Resources/unsafe-fifo")
    fifo.type = tarfile.FIFOTYPE
    fifo.mode = 0o644
    archive.addfile(fifo)
PY

if fifo_output="$(
  ARCHIVE_PATH="${UNSAFE_FIFO_ARCHIVE}" \
    OUTPUT_DIR="${TMP_ROOT}/unsafe-fifo-downloaded" \
    APP_BASENAME="TestApp.app" \
    bash "${ROOT_DIR}/scripts/release/extract-app-artifact.sh" 2>&1
)"; then
  echo "Archive with a FIFO member was incorrectly accepted." >&2
  exit 1
fi
if [[ "${fifo_output}" != *"Unsupported archive member type"* ]]; then
  echo "FIFO member was not rejected during archive prevalidation." >&2
  printf '%s\n' "${fifo_output}" >&2
  exit 1
fi

printf 'App artifact handoff preserved and verified executable permissions.\n'
