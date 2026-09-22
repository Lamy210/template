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
if (($# > 1)); then
  usage
  exit 2
fi

command -v gh >/dev/null 2>&1 || {
  echo "gh is required." >&2
  exit 2
}
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required." >&2
  exit 2
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work_root="$(mktemp -d "${TMPDIR:-/tmp}/main-ruleset-audit.XXXXXX")"
cleanup() {
  rm -rf "${work_root}"
}
trap cleanup EXIT

rulesets_json="${work_root}/rulesets.json"
gh api --paginate --slurp -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2026-03-10' "repos/${repository}/rulesets?targets=branch&includes_parents=true&per_page=100" >"${rulesets_json}"

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
    and ruleset.get("source") == repository
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
gh api -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2026-03-10' "repos/${repository}/rulesets/${candidate_id}?includes_parents=true" >"${detail_json}"

python3 "${repo_root}/scripts/ci/audit_main_ruleset.py" "${detail_json}" "${repository}"
