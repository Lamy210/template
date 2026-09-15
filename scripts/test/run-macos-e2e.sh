#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_WORKSPACE:?GITHUB_WORKSPACE is required}"
: "${WORKING_DIRECTORY:?WORKING_DIRECTORY is required}"
: "${SCHEME:?SCHEME is required}"
: "${TEST_DESTINATION:?TEST_DESTINATION is required}"

PROJECT_PATH="${PROJECT_PATH:-}"
WORKSPACE_PATH="${WORKSPACE_PATH:-}"
TEST_PLAN="${TEST_PLAN:-}"

safe_relative_path() {
  local value="$1"
  [[ -n "${value}" && "${value}" != /* && "${value}" != *".."* ]]
}

safe_relative_path "${WORKING_DIRECTORY}" || {
  echo "working_directory must be repository-relative" >&2
  exit 2
}

if [[ -n "${PROJECT_PATH}" && -n "${WORKSPACE_PATH}" ]] || [[ -z "${PROJECT_PATH}" && -z "${WORKSPACE_PATH}" ]]; then
  echo "exactly one of project_path or workspace_path is required" >&2
  exit 2
fi

if [[ -n "${PROJECT_PATH}" ]]; then
  safe_relative_path "${PROJECT_PATH}" || exit 2
else
  safe_relative_path "${WORKSPACE_PATH}" || exit 2
fi

xcodebuild -version
