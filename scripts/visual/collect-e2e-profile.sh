#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${GITHUB_WORKSPACE:?GITHUB_WORKSPACE is required}"
: "${VISUAL_PROFILE_ID:?VISUAL_PROFILE_ID is required}"
: "${CURRENT_SHA:?CURRENT_SHA is required}"

bash "${ROOT}/scripts/visual/collect-metadata.sh" \
  --output "${GITHUB_WORKSPACE}/artifacts/visual/profile.json" \
  --profile-id "${VISUAL_PROFILE_ID}" \
  --current-sha "${CURRENT_SHA}" \
  --runner-family "macos-26" \
  --architecture "${RUNNER_ARCH:-unknown}" \
  --xcode-policy "Xcode 26.6" \
  --locale "${LANG:-en_US.UTF-8}" \
  --language "en" \
  --timezone "${TZ:-UTC}" \
  --appearance "controlled-by-test" \
  --display-scale "2x" \
  --capture-geometry "window-or-element" \
  --fixture-version "fixture-v1" \
  --capture-contract-version 1 \
  --comparator-schema-version 1
