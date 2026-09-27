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
if [[ -n "${GITHUB_REPOSITORY:-}" && "${GITHUB_REPOSITORY,,}" == "${repository,,}" ]]; then
  echo "This proof refuses the current repository from GITHUB_REPOSITORY. Use a separate disposable repository." >&2
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

for command_name in gh git python3; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

github_repository_from_remote() {
  python3 - "$1" <<'PY'
import re
import sys
from urllib.parse import urlparse

value = sys.argv[1].strip()
if not value:
    raise SystemExit(0)

path = None
scp = re.fullmatch(r"[^@]+@github\.com:(.+)", value, re.IGNORECASE)
if scp is not None:
    path = scp.group(1)
else:
    parsed = urlparse(value)
    if parsed.hostname is None or parsed.hostname.casefold() != "github.com":
        raise SystemExit(0)
    path = parsed.path.lstrip("/")

path = path.rstrip("/")
if path.endswith(".git"):
    path = path[:-4]
parts = path.split("/")
if len(parts) != 2 or any(
    re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None for part in parts
):
    raise SystemExit("GitHub origin URL does not resolve to owner/repo")
print("/".join(parts))
PY
}

origin_url="$(git -C "${repo_root}" remote get-url origin 2>/dev/null || true)"
if [[ -n "${origin_url}" ]]; then
  if ! local_repository="$(github_repository_from_remote "${origin_url}")"; then
    echo "Unable to resolve the local GitHub origin safely: ${origin_url}" >&2
    exit 2
  fi
  if [[ -n "${local_repository}" && "${local_repository,,}" == "${repository,,}" ]]; then
    echo "This proof refuses the local checkout repository. Use a separate disposable repository." >&2
    exit 2
  fi
fi

mutation_result="$(mktemp "${TMPDIR:-/tmp}/release-tag-mutation.XXXXXX")"
cleanup() {
  rm -f "${mutation_result}"
}
trap cleanup EXIT

confirmed_ruleset_rejection() {
  grep -F "Repository rule violations found" "${mutation_result}" >/dev/null
}

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

repository_identity() {
  gh api "${api_headers[@]}" "repos/${repository}" |
    python3 -c '
import json
import re
import sys

expected = sys.argv[1]
try:
    document = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError) as error:
    raise SystemExit(f"repository identity response is invalid JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("repository identity response must be an object")

repository_id = document.get("id")
full_name = document.get("full_name")
if type(repository_id) is not int or repository_id <= 0:
    raise SystemExit("repository identity response has no positive integer id")
if (
    not isinstance(full_name, str)
    or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) is None
):
    raise SystemExit("repository identity response has no canonical full_name")
if full_name.casefold() != expected.casefold():
    raise SystemExit(
        f"repository full_name mismatch: expected {expected!r}, got {full_name!r}"
    )

print(repository_id)
print(full_name.casefold())
' "${repository}"
}

if ! initial_identity_output="$(repository_identity)"; then
  echo "Unable to bind disposable repository identity before mutation." >&2
  exit 3
fi
mapfile -t initial_identity <<<"${initial_identity_output}"
if (("${#initial_identity[@]}" != 2)); then
  echo "Disposable repository identity output was malformed." >&2
  exit 3
fi
initial_repository_id="${initial_identity[0]}"
initial_repository_name="${initial_identity[1]}"

require_repository_identity_stable() {
  local current_identity_output
  local -a current_identity

  if ! current_identity_output="$(repository_identity)"; then
    echo "Unable to rebind disposable repository identity." >&2
    return 1
  fi
  mapfile -t current_identity <<<"${current_identity_output}"
  if (("${#current_identity[@]}" != 2)); then
    echo "Disposable repository identity rebind output was malformed." >&2
    return 1
  fi
  if [[ "${current_identity[0]}" != "${initial_repository_id}" ||
        "${current_identity[1]}" != "${initial_repository_name}" ]]; then
    echo "Disposable repository identity changed during release-tag proof." >&2
    return 1
  fi
}

ref_endpoint="repos/${repository}/git/ref/tags/${tag}"

ref_sha() {
  gh api "${api_headers[@]}" "${ref_endpoint}" |
    python3 -c '
import json
import re
import sys

expected_ref = sys.argv[1]
try:
    document = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError) as error:
    raise SystemExit(f"tag ref response is invalid JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("tag ref response must be an object")
if document.get("ref") != expected_ref:
    raise SystemExit(
        f"tag ref identity mismatch: expected {expected_ref!r}, "
        f"got {document.get("ref")!r}"
    )
obj = document.get("object")
if not isinstance(obj, dict):
    raise SystemExit("tag ref response is missing object metadata")
if obj.get("type") != "commit":
    raise SystemExit("tag ref must resolve directly to a commit")
sha = obj.get("sha")
if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("tag ref response does not contain a canonical commit SHA")
print(sha)
' "refs/tags/${tag}"
}

echo "WARNING: destructive proof against disposable repository ${repository}; the created tag is expected to remain."

gh api "${api_headers[@]}" "repos/${repository}/commits/${initial_sha}" >/dev/null
gh api "${api_headers[@]}" "repos/${repository}/commits/${move_sha}" >/dev/null

if gh api "${api_headers[@]}" "${ref_endpoint}" >/dev/null 2>&1; then
  echo "Refusing to reuse existing tag refs/tags/${tag}." >&2
  exit 3
fi

require_repository_identity_stable || exit 3

gh api "${api_headers[@]}" --method POST "repos/${repository}/git/refs" -f "ref=refs/tags/${tag}" -f "sha=${initial_sha}" >/dev/null

created_sha="$(ref_sha)"
if [[ "${created_sha}" != "${initial_sha}" ]]; then
  echo "Created tag does not resolve to the requested initial SHA." >&2
  exit 3
fi
echo "creation succeeded: refs/tags/${tag} -> ${initial_sha}"

require_repository_identity_stable || exit 3

: >"${mutation_result}"
if gh api "${api_headers[@]}" --method PATCH "repos/${repository}/git/refs/tags/${tag}" -f "sha=${move_sha}" -F force=true >"${mutation_result}" 2>&1; then
  echo "update unexpectedly succeeded; immutable release-tag policy is NOT enforced." >&2
  exit 4
fi
if ! confirmed_ruleset_rejection; then
  echo "update failed but was not a confirmed repository-rule rejection." >&2
  cat "${mutation_result}" >&2
  exit 4
fi

after_update_sha="$(ref_sha)"
if [[ "${after_update_sha}" != "${initial_sha}" ]]; then
  echo "Update request failed but tag no longer points to initial SHA." >&2
  exit 4
fi
echo "update rejected; tag still points to initial SHA ${initial_sha}"

require_repository_identity_stable || exit 4

: >"${mutation_result}"
if gh api "${api_headers[@]}" --method DELETE "repos/${repository}/git/refs/tags/${tag}" >"${mutation_result}" 2>&1; then
  echo "deletion unexpectedly succeeded; immutable release-tag policy is NOT enforced." >&2
  exit 5
fi
if ! confirmed_ruleset_rejection; then
  echo "deletion failed but was not a confirmed repository-rule rejection." >&2
  cat "${mutation_result}" >&2
  exit 5
fi

after_delete_sha="$(ref_sha)"
if [[ "${after_delete_sha}" != "${initial_sha}" ]]; then
  echo "Deletion request failed but tag is missing or changed." >&2
  exit 5
fi
echo "deletion rejected; tag still exists after rejected deletion and points to ${initial_sha}"

require_repository_identity_stable || exit 5

echo "release-tag immutability proof passed for ${repository} refs/tags/${tag}"
