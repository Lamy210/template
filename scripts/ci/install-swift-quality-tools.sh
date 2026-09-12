#!/usr/bin/env bash
set -euo pipefail

SWIFTFORMAT_VERSION="${SWIFTFORMAT_VERSION:-0.63.0}"
SWIFTFORMAT_SHA256="${SWIFTFORMAT_SHA256:-28c7802e11fa5ae113d903066439c6bb1be20a8ac1ad9709c42616a7e273fb0f}"
SWIFTLINT_VERSION="${SWIFTLINT_VERSION:-0.65.1}"
SWIFTLINT_SHA256="${SWIFTLINT_SHA256:-c1e429b0599cf1b516f369a2d9ec04eaf0e436f3c12b637df8851fa52ff694d0}"

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
TOOLS_ROOT="${TEMP_ROOT%/}/swift-quality-tools"
SWIFTFORMAT_DIR="${TOOLS_ROOT}/swiftformat"
SWIFTLINT_DIR="${TOOLS_ROOT}/swiftlint"
SWIFTFORMAT_ZIP="${TOOLS_ROOT}/swiftformat.zip"
SWIFTLINT_ZIP="${TOOLS_ROOT}/swiftlint.zip"

rm -rf "${TOOLS_ROOT}"
mkdir -p "${SWIFTFORMAT_DIR}" "${SWIFTLINT_DIR}"

curl --fail --silent --show-error --location --retry 3 \
  --output "${SWIFTFORMAT_ZIP}" \
  "https://github.com/nicklockwood/SwiftFormat/releases/download/${SWIFTFORMAT_VERSION}/swiftformat.zip"
printf '%s  %s\n' "${SWIFTFORMAT_SHA256}" "${SWIFTFORMAT_ZIP}" | shasum -a 256 --check
unzip -q -j "${SWIFTFORMAT_ZIP}" -d "${SWIFTFORMAT_DIR}"

curl --fail --silent --show-error --location --retry 3 \
  --output "${SWIFTLINT_ZIP}" \
  "https://github.com/realm/SwiftLint/releases/download/${SWIFTLINT_VERSION}/portable_swiftlint.zip"
printf '%s  %s\n' "${SWIFTLINT_SHA256}" "${SWIFTLINT_ZIP}" | shasum -a 256 --check
unzip -q -j "${SWIFTLINT_ZIP}" -d "${SWIFTLINT_DIR}"

chmod +x "${SWIFTFORMAT_DIR}/swiftformat" "${SWIFTLINT_DIR}/swiftlint"
xattr -dr com.apple.quarantine "${SWIFTFORMAT_DIR}/swiftformat" 2>/dev/null || true
xattr -dr com.apple.quarantine "${SWIFTLINT_DIR}/swiftlint" 2>/dev/null || true

actual_swiftformat_version="$("${SWIFTFORMAT_DIR}/swiftformat" --version)"
actual_swiftlint_version="$("${SWIFTLINT_DIR}/swiftlint" version)"

if [[ "${actual_swiftformat_version}" != "${SWIFTFORMAT_VERSION}" ]]; then
  echo "SwiftFormat version mismatch: expected ${SWIFTFORMAT_VERSION}, got ${actual_swiftformat_version}" >&2
  exit 1
fi
if [[ "${actual_swiftlint_version}" != "${SWIFTLINT_VERSION}" ]]; then
  echo "SwiftLint version mismatch: expected ${SWIFTLINT_VERSION}, got ${actual_swiftlint_version}" >&2
  exit 1
fi

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "${SWIFTFORMAT_DIR}" >>"${GITHUB_PATH}"
  printf '%s\n' "${SWIFTLINT_DIR}" >>"${GITHUB_PATH}"
else
  printf 'SwiftFormat: %s\n' "${SWIFTFORMAT_DIR}/swiftformat"
  printf 'SwiftLint: %s\n' "${SWIFTLINT_DIR}/swiftlint"
fi
