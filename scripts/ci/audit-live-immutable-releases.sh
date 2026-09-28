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
repository_owner="${repository%%/*}"
repository_name="${repository#*/}"
if [[ "${repository_owner}" == "." || "${repository_owner}" == ".." ||
      "${repository_name}" == "." || "${repository_name}" == ".." ]]; then
  echo "repository contains an invalid owner or repository component." >&2
  exit 2
fi

for command_name in gh python3 mktemp rm sed tail; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
validator="${repo_root}/scripts/ci/validate-immutable-releases-setting.py"
[[ -f "${validator}" ]] || {
  echo "Immutable releases setting validator is unavailable: ${validator}" >&2
  exit 2
}

temp_root="$(mktemp -d)"
cleanup() {
  rm -rf "${temp_root}"
}
trap cleanup EXIT

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

repository_identity() {
  local metadata="$1"
  python3 - "${repository}" "${metadata}" <<'PY'
import json
from pathlib import Path
import re
import sys

expected_repository, path_text = sys.argv[1:]
try:
    document = json.loads(Path(path_text).read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as error:
    raise SystemExit(f"repository identity response is invalid JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("repository identity response must be a JSON object")

repository_id = document.get("id")
full_name = document.get("full_name")
if type(repository_id) is not int or repository_id <= 0:
    raise SystemExit("repository identity response has invalid id")
if (
    not isinstance(full_name, str)
    or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) is None
):
    raise SystemExit("repository identity response has invalid full_name")
if full_name.casefold() != expected_repository.casefold():
    raise SystemExit(
        f"repository full_name mismatch: expected {expected_repository!r}, "
        f"got {full_name!r}"
    )

print(repository_id)
print(full_name.casefold())
PY
}

initial_repository_json="${temp_root}/repository-before.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${initial_repository_json}"; then
  echo "Failed to resolve repository identity before immutable-release audit." >&2
  exit 3
fi
if ! initial_identity="$(repository_identity "${initial_repository_json}")"; then
  echo "Repository identity failed validation before immutable-release audit." >&2
  exit 3
fi
initial_repository_id="$(printf '%s\n' "${initial_identity}" | sed -n '1p')"
initial_repository_name="$(printf '%s\n' "${initial_identity}" | sed -n '2p')"
initial_repository_extra="$(printf '%s\n' "${initial_identity}" | sed -n '3p')"
if [[ -z "${initial_repository_id}" || -z "${initial_repository_name}" ||
      -n "${initial_repository_extra}" ]]; then
  echo "Repository identity output was malformed." >&2
  exit 3
fi

settings_json="${temp_root}/immutable-releases.json"
if ! gh api "${api_headers[@]}" --method GET \
  "repos/${repository}/immutable-releases" >"${settings_json}"; then
  echo "Unable to prove native immutable releases are enabled for ${repository}." >&2
  echo "The endpoint returns 404 when disabled and requires repository Administration(read) when enabled." >&2
  exit 4
fi

if ! setting_output="$(python3 "${validator}" --metadata "${settings_json}")"; then
  echo "Native immutable releases setting failed validation for ${repository}." >&2
  exit 4
fi

final_repository_json="${temp_root}/repository-after.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${final_repository_json}"; then
  echo "Failed to re-resolve repository identity after immutable-release audit." >&2
  exit 5
fi
if ! final_identity="$(repository_identity "${final_repository_json}")"; then
  echo "Repository identity failed final immutable-release audit validation." >&2
  exit 5
fi
final_repository_id="$(printf '%s\n' "${final_identity}" | sed -n '1p')"
final_repository_name="$(printf '%s\n' "${final_identity}" | sed -n '2p')"
final_repository_extra="$(printf '%s\n' "${final_identity}" | sed -n '3p')"
if [[ -z "${final_repository_id}" || -z "${final_repository_name}" ||
      -n "${final_repository_extra}" ]]; then
  echo "Final repository identity output was malformed." >&2
  exit 5
fi
if [[ "${final_repository_id}" != "${initial_repository_id}" ||
      "${final_repository_name}" != "${initial_repository_name}" ]]; then
  echo "Repository identity changed during immutable-release audit." >&2
  exit 5
fi

printf 'native immutable releases enabled for %s (%s)\n' \
  "${repository}" "$(printf '%s\n' "${setting_output}" | tail -n 1)"
