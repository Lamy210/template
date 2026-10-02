#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: audit-live-release-tag-ruleset.sh owner/repo

Read the active repository Ruleset named "Immutable release tags" and validate
its live configuration against the checked-in immutable release-tag contract.
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

work_root="$(mktemp -d "${TMPDIR:-/tmp}/release-tag-ruleset-audit.XXXXXX")"
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

select_candidate_id() {
  local metadata="$1"
  python3 - "${metadata}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    pages = json.load(handle)

if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
    raise SystemExit("Ruleset list response must be an array of page arrays")

rulesets = [ruleset for page in pages for ruleset in page]
active_tag_rulesets = [
    ruleset
    for ruleset in rulesets
    if isinstance(ruleset, dict)
    and ruleset.get("target") == "tag"
    and ruleset.get("enforcement") == "active"
]

if len(active_tag_rulesets) != 1:
    names = sorted(
        str(ruleset.get("name"))
        for ruleset in active_tag_rulesets
        if isinstance(ruleset.get("name"), str)
    )
    raise SystemExit(
        "Expected exactly one active tag Ruleset overall; "
        f"found {len(active_tag_rulesets)}: {names!r}"
    )

candidate = active_tag_rulesets[0]
if candidate.get("name") != "Immutable release tags":
    raise SystemExit(
        "The only active tag Ruleset must be named 'Immutable release tags'; "
        f"got {candidate.get('name')!r}"
    )

ruleset_id = candidate.get("id")
if type(ruleset_id) is not int or ruleset_id <= 0:
    raise SystemExit("Live release-tag Ruleset id must be a positive integer")
print(ruleset_id)
PY
}

initial_rulesets_json="${work_root}/rulesets-before.json"
if ! gh api --paginate --slurp "${api_headers[@]}" \
  "repos/${repository}/rulesets?targets=tag&includes_parents=true&per_page=100" >"${initial_rulesets_json}"; then
  echo "Failed to read release-tag Rulesets for ${repository}." >&2
  exit 3
fi
if ! candidate_id="$(select_candidate_id "${initial_rulesets_json}")"; then
  exit 3
fi

initial_repository_json="${work_root}/repository-before.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${initial_repository_json}"; then
  echo "Failed to read repository identity for ${repository}." >&2
  exit 4
fi
if ! initial_identity="$(validate_identity "${initial_repository_json}")"; then
  echo "Repository identity is invalid for ${repository}." >&2
  exit 4
fi

initial_detail_json="${work_root}/ruleset-before.json"
if ! gh api "${api_headers[@]}" \
  "repos/${repository}/rulesets/${candidate_id}?includes_parents=true" >"${initial_detail_json}"; then
  echo "Failed to read release-tag Ruleset ${candidate_id} for ${repository}." >&2
  exit 5
fi

middle_repository_json="${work_root}/repository-middle.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${middle_repository_json}"; then
  echo "Failed to re-read repository identity for ${repository}." >&2
  exit 6
fi
if ! middle_identity="$(validate_identity "${middle_repository_json}")"; then
  echo "Middle repository identity is invalid for ${repository}." >&2
  exit 6
fi
if [[ "${initial_identity}" != "${middle_identity}" ]]; then
  echo "Repository identity changed during release-tag Ruleset audit." >&2
  exit 6
fi

final_rulesets_json="${work_root}/rulesets-after.json"
if ! gh api --paginate --slurp "${api_headers[@]}" \
  "repos/${repository}/rulesets?targets=tag&includes_parents=true&per_page=100" >"${final_rulesets_json}"; then
  echo "Failed to re-read release-tag Rulesets for ${repository}." >&2
  exit 7
fi
if ! final_candidate_id="$(select_candidate_id "${final_rulesets_json}")"; then
  exit 7
fi
if [[ "${candidate_id}" != "${final_candidate_id}" ]]; then
  echo "Active release-tag Ruleset identity changed during audit." >&2
  exit 7
fi

final_detail_json="${work_root}/ruleset-after.json"
if ! gh api "${api_headers[@]}" \
  "repos/${repository}/rulesets/${final_candidate_id}?includes_parents=true" >"${final_detail_json}"; then
  echo "Failed to re-read release-tag Ruleset ${final_candidate_id} for ${repository}." >&2
  exit 8
fi

terminal_repository_json="${work_root}/repository-after.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${terminal_repository_json}"; then
  echo "Failed to re-read repository identity after final release-tag Ruleset read." >&2
  exit 9
fi
if ! terminal_identity="$(validate_identity "${terminal_repository_json}")"; then
  echo "Terminal repository identity is invalid for ${repository}." >&2
  exit 9
fi
if [[ "${initial_identity}" != "${terminal_identity}" ]]; then
  echo "Repository identity changed during final release-tag Ruleset verification." >&2
  exit 9
fi

python3 "${repo_root}/scripts/ci/audit_release_tag_ruleset.py" \
  "${final_detail_json}" "${repository}"
