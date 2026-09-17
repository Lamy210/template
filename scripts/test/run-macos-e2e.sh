#!/usr/bin/env bash
set -euo pipefail

validate_only=false
if (($# > 1)); then
  echo "usage: run-macos-e2e.sh [--validate-only]" >&2
  exit 2
fi
if (($# == 1)); then
  if [[ "$1" != "--validate-only" ]]; then
    echo "unknown argument: $1" >&2
    exit 2
  fi
  validate_only=true
fi

: "${GITHUB_WORKSPACE:?GITHUB_WORKSPACE is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
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
[[ -d "${GITHUB_WORKSPACE}/${WORKING_DIRECTORY}" ]] || {
  echo "working_directory does not exist: ${WORKING_DIRECTORY}" >&2
  exit 2
}

if [[ -n "${PROJECT_PATH}" && -n "${WORKSPACE_PATH}" ]] || [[ -z "${PROJECT_PATH}" && -z "${WORKSPACE_PATH}" ]]; then
  echo "exactly one of project_path or workspace_path is required" >&2
  exit 2
fi

if [[ -n "${PROJECT_PATH}" ]]; then
  safe_relative_path "${PROJECT_PATH}" || exit 2
  [[ -d "${GITHUB_WORKSPACE}/${WORKING_DIRECTORY}/${PROJECT_PATH}" ]] || {
    echo "project does not exist: ${PROJECT_PATH}" >&2
    exit 2
  }
else
  safe_relative_path "${WORKSPACE_PATH}" || exit 2
  [[ -d "${GITHUB_WORKSPACE}/${WORKING_DIRECTORY}/${WORKSPACE_PATH}" ]] || {
    echo "workspace does not exist: ${WORKSPACE_PATH}" >&2
    exit 2
  }
fi

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export TZ="${TZ:-UTC}"
export TEST_RANDOM_SEED="${TEST_RANDOM_SEED:-0}"
export TEST_FIXED_TIME="${TEST_FIXED_TIME:-2026-01-01T00:00:00Z}"
export TEST_DISABLE_ANIMATIONS="${TEST_DISABLE_ANIMATIONS:-1}"
export VISUAL_OUTPUT_DIR="${GITHUB_WORKSPACE}/artifacts/visual/current"
export E2E_DERIVED_DATA="${RUNNER_TEMP}/e2e-derived-data"
export E2E_RESULT_BUNDLE="${RUNNER_TEMP}/e2e.xcresult"

[[ ! -e "${GITHUB_WORKSPACE}/artifacts/visual" ]] || {
  echo "visual artifact path must not exist before E2E execution" >&2
  exit 2
}
[[ ! -e "${E2E_RESULT_BUNDLE}" ]] || {
  echo "E2E result bundle must not exist before E2E execution" >&2
  exit 2
}

if [[ "${validate_only}" == "true" ]]; then
  exit 0
fi

mkdir -p "${VISUAL_OUTPUT_DIR}"
cd "${GITHUB_WORKSPACE}"

run_build_for_testing() {
  if [[ -n "${PROJECT_PATH}" ]]; then
    if [[ -n "${TEST_PLAN}" ]]; then
      xcodebuild -project "${WORKING_DIRECTORY}/${PROJECT_PATH}" -scheme "${SCHEME}" -testPlan "${TEST_PLAN}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO build-for-testing
    else
      xcodebuild -project "${WORKING_DIRECTORY}/${PROJECT_PATH}" -scheme "${SCHEME}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO build-for-testing
    fi
  elif [[ -n "${TEST_PLAN}" ]]; then
    xcodebuild -workspace "${WORKING_DIRECTORY}/${WORKSPACE_PATH}" -scheme "${SCHEME}" -testPlan "${TEST_PLAN}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO build-for-testing
  else
    xcodebuild -workspace "${WORKING_DIRECTORY}/${WORKSPACE_PATH}" -scheme "${SCHEME}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO build-for-testing
  fi
}

run_test_without_building() {
  if [[ -n "${PROJECT_PATH}" ]]; then
    if [[ -n "${TEST_PLAN}" ]]; then
      xcodebuild -project "${WORKING_DIRECTORY}/${PROJECT_PATH}" -scheme "${SCHEME}" -testPlan "${TEST_PLAN}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO -resultBundlePath "${E2E_RESULT_BUNDLE}" test-without-building
    else
      xcodebuild -project "${WORKING_DIRECTORY}/${PROJECT_PATH}" -scheme "${SCHEME}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO -resultBundlePath "${E2E_RESULT_BUNDLE}" test-without-building
    fi
  elif [[ -n "${TEST_PLAN}" ]]; then
    xcodebuild -workspace "${WORKING_DIRECTORY}/${WORKSPACE_PATH}" -scheme "${SCHEME}" -testPlan "${TEST_PLAN}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO -resultBundlePath "${E2E_RESULT_BUNDLE}" test-without-building
  else
    xcodebuild -workspace "${WORKING_DIRECTORY}/${WORKSPACE_PATH}" -scheme "${SCHEME}" -destination "${TEST_DESTINATION}" -derivedDataPath "${E2E_DERIVED_DATA}" -parallel-testing-enabled NO -resultBundlePath "${E2E_RESULT_BUNDLE}" test-without-building
  fi
}

run_build_for_testing
run_test_without_building
