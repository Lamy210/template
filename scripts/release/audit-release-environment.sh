#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: audit-release-environment.sh owner/repo

Read the repository's release Environment and deployment branch policies, then
validate that only the repository default branch is selected. This command is
read-only.
EOF
}

repository="${1:-${GITHUB_REPOSITORY:-}}"
if [[ ! "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || (($# > 1)); then
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
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/release-environment-audit.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

default_branch="$(
  gh api \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2026-03-10' \
    "repos/${repository}" \
    --jq '.default_branch'
)"
if [[ -z "${default_branch}" || "${default_branch}" == null ]]; then
  echo "Unable to resolve repository default branch." >&2
  exit 3
fi

gh api \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2026-03-10' \
  "repos/${repository}/environments/release" \
  >"${temp_root}/environment.json"

gh api \
  --paginate \
  --slurp \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2026-03-10' \
  "repos/${repository}/environments/release/deployment-branch-policies?per_page=100" \
  >"${temp_root}/policies.json"

python3 "${repo_root}/scripts/release/audit-release-environment.py" \
  --environment "${temp_root}/environment.json" \
  --policies "${temp_root}/policies.json" \
  --default-branch "${default_branch}"
