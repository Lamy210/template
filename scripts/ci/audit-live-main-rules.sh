#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: audit-live-main-rules.sh owner/repo

Read GitHub's effective active rules for the repository default branch and
validate them against the Solo governance contract. This command is read-only.
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

work_root="$(mktemp -d "${TMPDIR:-/tmp}/main-effective-rules-audit.XXXXXX")"
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
if ! default_branch="$(read_default_branch "${initial_json}")"; then
  echo "Unable to resolve repository default branch." >&2
  exit 3
fi

encoded_branch="$(
  python3 - "${default_branch}" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
)"

rules_json="${work_root}/effective-rules.json"
if ! gh api \
  --paginate \
  --slurp \
  "${api_headers[@]}" \
  "repos/${repository}/rules/branches/${encoded_branch}?per_page=100" >"${rules_json}"; then
  echo "Failed to read effective default-branch rules for ${repository}." >&2
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
  "${default_branch}" != "${final_default_branch}" ]]; then
  echo "Repository identity or default branch changed during the effective-rules audit." >&2
  exit 5
fi

final_rules_json="${work_root}/effective-rules-after.json"
if ! gh api \
  --paginate \
  --slurp \
  "${api_headers[@]}" \
  "repos/${repository}/rules/branches/${encoded_branch}?per_page=100" >"${final_rules_json}"; then
  echo "Failed to re-read effective default-branch rules for ${repository}." >&2
  exit 6
fi

terminal_json="${work_root}/repository-terminal.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${terminal_json}"; then
  echo "Failed to re-read repository identity after final effective-rules read." >&2
  exit 7
fi
if ! terminal_identity="$(validate_identity "${terminal_json}")"; then
  echo "Terminal repository identity is invalid for ${repository}." >&2
  exit 7
fi
if ! terminal_default_branch="$(read_default_branch "${terminal_json}")"; then
  echo "Unable to re-resolve repository default branch after final rules read." >&2
  exit 7
fi

if [[ "${initial_identity}" != "${terminal_identity}" ||
  "${default_branch}" != "${terminal_default_branch}" ]]; then
  echo "Repository identity or default branch changed during final effective-rules verification." >&2
  exit 7
fi

python3 "${repo_root}/scripts/ci/audit_effective_rules.py" "${final_rules_json}"
