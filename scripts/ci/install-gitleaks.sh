#!/usr/bin/env bash
set -euo pipefail

GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.30.1}"
GITLEAKS_SHA256="${GITLEAKS_SHA256:-551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb}"

TEMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
TOOLS_ROOT="${TEMP_ROOT%/}/gitleaks-${GITLEAKS_VERSION}"
ARCHIVE_PATH="${TEMP_ROOT%/}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"

rm -rf "${TOOLS_ROOT}"
mkdir -p "${TOOLS_ROOT}"

curl --fail --silent --show-error --location --retry 3 \
  --output "${ARCHIVE_PATH}" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
printf '%s  %s\n' "${GITLEAKS_SHA256}" "${ARCHIVE_PATH}" | shasum -a 256 --check

tar -xzf "${ARCHIVE_PATH}" -C "${TOOLS_ROOT}" gitleaks
chmod +x "${TOOLS_ROOT}/gitleaks"

actual_version="$("${TOOLS_ROOT}/gitleaks" version)"
if [[ "${actual_version}" != "${GITLEAKS_VERSION}" ]]; then
  echo "Gitleaks version mismatch: expected ${GITLEAKS_VERSION}, got ${actual_version}" >&2
  exit 1
fi

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "${TOOLS_ROOT}" >>"${GITHUB_PATH}"
else
  printf '%s\n' "${TOOLS_ROOT}/gitleaks"
fi
