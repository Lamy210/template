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

encoded_branch="$(
  python3 - "${default_branch}" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
)"

gh api \
  --paginate \
  --slurp \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2026-03-10' \
  "repos/${repository}/rules/branches/${encoded_branch}?per_page=100" |
  python3 "${repo_root}/scripts/ci/audit_effective_rules.py" -
