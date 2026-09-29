#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 owner/repo" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

repository="$1"
if [[ ! "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "repository must use canonical owner/repo form." >&2
  exit 2
fi

for command_name in gh python3 mktemp rm; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
validator="${repo_root}/scripts/ci/validate-repository-merge-settings.py"
[[ -f "${validator}" ]] || {
  echo "Repository merge settings validator is unavailable: ${validator}" >&2
  exit 2
}

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/repository-merge-settings.XXXXXX")"
cleanup() {
  rm -rf "${temp_root}"
}
trap cleanup EXIT

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

validate_snapshot() {
  local metadata="$1"
  python3 "${validator}" \
    --metadata "${metadata}" \
    --repository "${repository}"
}

initial_json="${temp_root}/repository-before.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${initial_json}"; then
  echo "Failed to read repository merge settings for ${repository}." >&2
  exit 3
fi
if ! initial_state="$(validate_snapshot "${initial_json}")"; then
  echo "Repository merge settings do not match the template policy for ${repository}." >&2
  exit 4
fi

final_json="${temp_root}/repository-after.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${final_json}"; then
  echo "Failed to re-read repository merge settings for ${repository}." >&2
  exit 5
fi
if ! final_state="$(validate_snapshot "${final_json}")"; then
  echo "Final repository merge settings do not match the template policy for ${repository}." >&2
  exit 5
fi

if [[ "${initial_state}" != "${final_state}" ]]; then
  echo "Repository identity or merge settings changed during the audit." >&2
  exit 5
fi

printf 'repository merge settings match the template policy for %s\n' "${repository}"
