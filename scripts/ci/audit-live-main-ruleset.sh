#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: audit-live-main-ruleset.sh owner/repo

Read the active repository Ruleset named "Solo default branch" and validate its
live configuration against the checked-in Solo default-branch contract.
This command is read-only.
EOF
}

repository="${1:-${GITHUB_REPOSITORY:-}}"
if [[ ! "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  usage
  exit 2
fi
repository_owner="${repository%%/*}"
repository_name="${repository#*/}"
if [[ "${repository_owner}" == "." || "${repository_owner}" == ".." ||
  "${repository_name}" == "." || "${repository_name}" == ".." ]]; then
  echo "repository must use canonical owner/repo form." >&2
  exit 2
fi
if (($# > 1)); then
  usage
  exit 2
fi

for command_name in gh python3 mktemp rm; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
identity_validator="${repo_root}/scripts/common/validate-repository-identity.py"
[[ -f "${identity_validator}" ]] || {
  echo "Repository identity validator is unavailable: ${identity_validator}" >&2
  exit 2
}

work_root="$(mktemp -d "${TMPDIR:-/tmp}/main-ruleset-audit.XXXXXX")"
cleanup() {
  rm -rf "${work_root}"
}
trap cleanup EXIT

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

validate_identity() {
  local metadata="$1"
  python3 "${identity_validator}" \
    --metadata "${metadata}" \
    --repository "${repository}"
}

read_default_branch() {
  local metadata="$1"
  python3 - "${metadata}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    document = json.load(handle)

default_branch = document.get("default_branch")
if not isinstance(default_branch, str) or not default_branch:
    raise SystemExit("repository default_branch must be a non-empty string")
print(default_branch)
PY
}

initial_json="${work_root}/repository-before.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${initial_json}"; then
  echo "Failed to read repository identity for ${repository}." >&2
  exit 3
fi
if ! initial_identity="$(validate_identity "${initial_json}")"; then
  echo "Repository identity is invalid for ${repository}." >&2
  exit 3
fi
if ! initial_default_branch="$(read_default_branch "${initial_json}")"; then
  echo "Unable to resolve repository default branch." >&2
  exit 3
fi

rulesets_json="${work_root}/rulesets.json"
if ! gh api --paginate --slurp "${api_headers[@]}" \
  "repos/${repository}/rulesets?targets=branch&includes_parents=true&per_page=100" >"${rulesets_json}"; then
  echo "Failed to read repository Rulesets for ${repository}." >&2
  exit 4
fi

candidate_id="$(
  python3 - "${rulesets_json}" "${repository}" <<'PY'
import json
import sys

path, repository = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    pages = json.load(handle)

if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
    raise SystemExit("Ruleset list response must be an array of page arrays")

rulesets = [ruleset for page in pages for ruleset in page]
candidates = [
    ruleset
    for ruleset in rulesets
    if isinstance(ruleset, dict)
    and ruleset.get("name") == "Solo default branch"
    and ruleset.get("target") == "branch"
    and ruleset.get("enforcement") == "active"
    and ruleset.get("source_type") == "Repository"
    and isinstance(ruleset.get("source"), str)
    and ruleset["source"].casefold() == repository.casefold()
]

if len(candidates) != 1:
    raise SystemExit(
        "Expected exactly one active repository Ruleset named 'Solo default branch'; "
        f"found {len(candidates)}"
    )

ruleset_id = candidates[0].get("id")
if type(ruleset_id) is not int or ruleset_id <= 0:
    raise SystemExit("Live Solo default-branch Ruleset id must be a positive integer")
print(ruleset_id)
PY
)"

detail_json="${work_root}/ruleset.json"
if ! gh api "${api_headers[@]}" \
  "repos/${repository}/rulesets/${candidate_id}?includes_parents=true" >"${detail_json}"; then
  echo "Failed to read Ruleset ${candidate_id} for ${repository}." >&2
  exit 4
fi

final_json="${work_root}/repository-after.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${final_json}"; then
  echo "Failed to re-read repository identity for ${repository}." >&2
  exit 5
fi
if ! final_identity="$(validate_identity "${final_json}")"; then
  echo "Final repository identity is invalid for ${repository}." >&2
  exit 5
fi
if ! final_default_branch="$(read_default_branch "${final_json}")"; then
  echo "Unable to re-resolve repository default branch." >&2
  exit 5
fi

if [[ "${initial_identity}" != "${final_identity}" ||
  "${initial_default_branch}" != "${final_default_branch}" ]]; then
  echo "Repository identity or default branch changed during the main-Ruleset audit." >&2
  exit 5
fi

python3 "${repo_root}/scripts/ci/audit_main_ruleset.py" "${detail_json}" "${repository}"
