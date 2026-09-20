#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  prove-release-tag-immutability.sh \
    --repository owner/disposable-repo \
    --confirm-disposable owner/disposable-repo \
    --tag v0.0.1 \
    --initial-sha <40-lowercase-hex> \
    --move-sha <different-40-lowercase-hex>

DESTRUCTIVE PROOF FOR A DISPOSABLE REPOSITORY ONLY.

The command creates the requested release tag and intentionally proves that the
tag cannot then be moved or deleted. With the correct immutable-tag Ruleset,
the created tag remains in the disposable repository permanently.
EOF
}

repository=""
confirmed_repository=""
tag=""
initial_sha=""
move_sha=""

while (($#)); do
  case "$1" in
    --repository)
      repository="${2:-}"
      shift 2
      ;;
    --confirm-disposable)
      confirmed_repository="${2:-}"
      shift 2
      ;;
    --tag)
      tag="${2:-}"
      shift 2
      ;;
    --initial-sha)
      initial_sha="${2:-}"
      shift 2
      ;;
    --move-sha)
      move_sha="${2:-}"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "--repository must be owner/repo." >&2
  exit 2
fi
if [[ "${confirmed_repository}" != "${repository}" ]]; then
  echo "--confirm-disposable must exactly equal --repository." >&2
  exit 2
fi
if [[ -n "${GITHUB_REPOSITORY:-}" && "${GITHUB_REPOSITORY}" == "${repository}" ]]; then
  echo "This proof refuses the current repository. Use a separate disposable repository." >&2
  exit 2
fi
if [[ ! "${tag}" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "--tag must be canonical stable SemVer in vX.Y.Z form." >&2
  exit 2
fi
if [[ ! "${initial_sha}" =~ ^[0-9a-f]{40}$ ]] || [[ ! "${move_sha}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "--initial-sha and --move-sha must be 40 lowercase hexadecimal characters." >&2
  exit 2
fi
if [[ "${initial_sha}" == "${move_sha}" ]]; then
  echo "--initial-sha and --move-sha must be distinct commits." >&2
  exit 2
fi

command -v gh >/dev/null 2>&1 || {
  echo "gh is required." >&2
  exit 2
}

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)
ref_endpoint="repos/${repository}/git/ref/tags/${tag}"

ref_sha() {
  gh api "${api_headers[@]}" "${ref_endpoint}" |
    python3 -c '
import json
import re
import sys

document = json.load(sys.stdin)
obj = document.get("object")
sha = obj.get("sha") if isinstance(obj, dict) else None
if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("tag ref response does not contain a canonical commit SHA")
print(sha)
'
}

echo "WARNING: destructive proof against disposable repository ${repository}; the created tag is expected to remain."

gh api "${api_headers[@]}" "repos/${repository}/commits/${initial_sha}" >/dev/null
gh api "${api_headers[@]}" "repos/${repository}/commits/${move_sha}" >/dev/null

if gh api "${api_headers[@]}" "${ref_endpoint}" >/dev/null 2>&1; then
  echo "Refusing to reuse existing tag refs/tags/${tag}." >&2
  exit 3
fi

gh api "${api_headers[@]}"   --method POST   "repos/${repository}/git/refs"   -f "ref=refs/tags/${tag}"   -f "sha=${initial_sha}"   >/dev/null

created_sha="$(ref_sha)"
if [[ "${created_sha}" != "${initial_sha}" ]]; then
  echo "Created tag does not resolve to the requested initial SHA." >&2
  exit 3
fi
echo "creation succeeded: refs/tags/${tag} -> ${initial_sha}"

if gh api "${api_headers[@]}"   --method PATCH   "repos/${repository}/git/refs/tags/${tag}"   -f "sha=${move_sha}"   -F force=true   >/dev/null 2>&1; then
  echo "update unexpectedly succeeded; immutable release-tag policy is NOT enforced." >&2
  exit 4
fi

after_update_sha="$(ref_sha)"
if [[ "${after_update_sha}" != "${initial_sha}" ]]; then
  echo "Update request failed but tag no longer points to initial SHA." >&2
  exit 4
fi
echo "update rejected; tag still points to initial SHA ${initial_sha}"

if gh api "${api_headers[@]}"   --method DELETE   "repos/${repository}/git/refs/tags/${tag}"   >/dev/null 2>&1; then
  echo "deletion unexpectedly succeeded; immutable release-tag policy is NOT enforced." >&2
  exit 5
fi

after_delete_sha="$(ref_sha)"
if [[ "${after_delete_sha}" != "${initial_sha}" ]]; then
  echo "Deletion request failed but tag is missing or changed." >&2
  exit 5
fi
echo "deletion rejected; tag still exists after rejected deletion and points to ${initial_sha}"

echo "release-tag immutability proof passed for ${repository} refs/tags/${tag}"
