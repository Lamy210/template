#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  apply-repository-merge-settings.sh \
    --repository owner/repo \
    --confirm-repository owner/repo \
    --apply

Applies the template's repository merge-policy contract:
  squash merge=true
  merge commits=false
  rebase merge=false
  delete merged head branches=true

This command mutates repository settings and requires repository Administration.
EOF
}

repository=""
confirmed_repository=""
apply=false

while (($#)); do
  case "$1" in
    --repository)
      repository="${2:-}"
      shift 2
      ;;
    --confirm-repository)
      confirmed_repository="${2:-}"
      shift 2
      ;;
    --apply)
      apply=true
      shift
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
  echo "--repository must use canonical owner/repo form." >&2
  exit 2
fi
repository_owner="${repository%%/*}"
repository_name="${repository#*/}"
if [[ "${repository_owner}" == "." || "${repository_owner}" == ".." ||
  "${repository_name}" == "." || "${repository_name}" == ".." ]]; then
  echo "--repository must use canonical owner/repo form." >&2
  exit 2
fi
if [[ "${confirmed_repository}" != "${repository}" ]]; then
  echo "--confirm-repository must exactly equal --repository." >&2
  exit 2
fi
if [[ "${apply}" != true ]]; then
  echo "--apply is required because this command mutates repository settings." >&2
  exit 2
fi

if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  echo "Refusing repository governance mutation from GitHub Actions; run from a trusted local operator session." >&2
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
if [[ ! -f "${validator}" || -L "${validator}" ]]; then
  echo "Repository merge settings validator must be a regular non-symlink file: ${validator}" >&2
  exit 2
fi

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/apply-repository-merge-settings.XXXXXX")"
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
  python3 - "${repo_root}" "${repository}" "${metadata}" <<'PY'
from pathlib import Path
import re
import sys

repo_root, expected_repository, metadata_path = sys.argv[1:]
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from scripts.common.bounded_json import BoundedJsonError, load_bounded_json_file

try:
    document = load_bounded_json_file(
        Path(metadata_path),
        label="repository identity response",
    )
except BoundedJsonError as error:
    raise SystemExit(str(error)) from error
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
owner, name = full_name.split("/", 1)
if owner in {".", ".."} or name in {".", ".."}:
    raise SystemExit("repository identity response has unsafe full_name")
if full_name.casefold() != expected_repository.casefold():
    raise SystemExit(
        f"repository full_name mismatch: expected {expected_repository!r}, got {full_name!r}"
    )

print(repository_id)
print(full_name.casefold())
PY
}

initial_json="${temp_root}/repository-before.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${initial_json}"; then
  echo "Failed to resolve repository identity before merge-policy update." >&2
  exit 3
fi
if ! initial_identity="$(repository_identity "${initial_json}")"; then
  echo "Repository identity failed validation before merge-policy update." >&2
  exit 3
fi

patch_json="${temp_root}/repository-patch.json"
if ! gh api "${api_headers[@]}" --method PATCH "repos/${repository}" \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true >"${patch_json}"; then
  echo "Failed to apply repository merge-policy settings." >&2
  exit 4
fi

final_json="${temp_root}/repository-after.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${final_json}"; then
  echo "Failed to re-read repository after merge-policy update." >&2
  exit 5
fi
if ! final_identity="$(repository_identity "${final_json}")"; then
  echo "Repository identity failed validation after merge-policy update." >&2
  exit 5
fi
if [[ "${initial_identity}" != "${final_identity}" ]]; then
  echo "Repository identity changed during merge-policy update." >&2
  exit 5
fi

if ! python3 "${validator}" \
  --metadata "${final_json}" \
  --repository "${repository}" >/dev/null; then
  echo "Repository merge-policy update did not converge to the template contract." >&2
  exit 5
fi

printf 'repository merge settings applied and verified for %s\n' "${repository}"
