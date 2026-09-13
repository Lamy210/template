#!/usr/bin/env bash
set -euo pipefail

: "${APP_PATH:?APP_PATH is required}"
: "${EXECUTABLE_NAME:?EXECUTABLE_NAME is required}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Application bundle not found: ${APP_PATH}" >&2
  exit 1
fi

if [[ "${EXECUTABLE_NAME}" == */* || "${EXECUTABLE_NAME}" == "." || "${EXECUTABLE_NAME}" == ".." ]]; then
  echo "CFBundleExecutable must be a basename: ${EXECUTABLE_NAME}" >&2
  exit 1
fi

executable_path="${APP_PATH}/Contents/MacOS/${EXECUTABLE_NAME}"
if [[ -L "${executable_path}" ]]; then
  echo "Bundle executable must not be a symbolic link: ${executable_path}" >&2
  exit 1
fi
if [[ ! -f "${executable_path}" ]]; then
  echo "Bundle executable not found: ${executable_path}" >&2
  exit 1
fi
if [[ ! -x "${executable_path}" ]]; then
  echo "Bundle executable is not executable: ${executable_path}" >&2
  exit 1
fi
