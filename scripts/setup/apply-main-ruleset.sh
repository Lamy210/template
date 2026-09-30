#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  apply-main-ruleset.sh \
    --repository owner/repo \
    --confirm-repository owner/repo \
    --ruleset-id 123456 \
    --confirm-ruleset-id 123456 \
    --apply

Reconciles one existing repository-owned default-branch Ruleset to the checked-in
rulesets/main-solo.json contract.

This command mutates repository Ruleset settings and requires repository
Administration (write). It never discovers, creates, deletes, or disables
Rulesets automatically.
EOF
}

repository=""
confirmed_repository=""
ruleset_id=""
confirmed_ruleset_id=""
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
    --ruleset-id)
      ruleset_id="${2:-}"
      shift 2
      ;;
    --confirm-ruleset-id)
      confirmed_ruleset_id="${2:-}"
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
if [[ ! "${ruleset_id}" =~ ^[1-9][0-9]*$ ]]; then
  echo "--ruleset-id must be a positive canonical decimal integer." >&2
  exit 2
fi
if [[ "${confirmed_ruleset_id}" != "${ruleset_id}" ]]; then
  echo "--confirm-ruleset-id must exactly equal --ruleset-id." >&2
  exit 2
fi
if [[ "${apply}" != true ]]; then
  echo "--apply is required because this command mutates repository Ruleset settings." >&2
  exit 2
fi

for command_name in gh python3 mktemp rm; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
desired_ruleset="${repo_root}/rulesets/main-solo.json"
offline_validator="${repo_root}/scripts/ci/validate_rulesets.py"
live_validator="${repo_root}/scripts/ci/audit_main_ruleset.py"

for required_file in "${desired_ruleset}" "${offline_validator}" "${live_validator}"; do
  [[ -f "${required_file}" ]] || {
    echo "Required Ruleset control file is unavailable: ${required_file}" >&2
    exit 2
  }
done

if ! python3 "${offline_validator}" >/dev/null; then
  echo "Checked-in Ruleset desired state failed offline validation; refusing mutation." >&2
  exit 3
fi

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/apply-main-ruleset.XXXXXX")"
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

expected_repository, metadata_path = sys.argv[1:]
try:
    document = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as error:
    raise SystemExit(f"repository identity response is invalid JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("repository identity response must be a JSON object")

repository_id = document.get("id")
full_name = document.get("full_name")
default_branch = document.get("default_branch")

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
if not isinstance(default_branch, str) or not default_branch or any(
    character.isspace() or ord(character) < 32 for character in default_branch
):
    raise SystemExit("repository identity response has invalid default_branch")

print(f"{repository_id}\t{full_name.casefold()}\t{default_branch}")
PY
}

ruleset_identity() {
  local metadata="$1"
  local expected_default_branch="$2"
  python3 - "${repository}" "${ruleset_id}" "${expected_default_branch}" "${metadata}" <<'PY'
import json
from pathlib import Path
import re
import sys

expected_repository, expected_id_text, default_branch, metadata_path = sys.argv[1:]
expected_id = int(expected_id_text)

try:
    document = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as error:
    raise SystemExit(f"Ruleset identity response is invalid JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("Ruleset identity response must be a JSON object")

ruleset_id = document.get("id")
source = document.get("source")
source_type = document.get("source_type")
target = document.get("target")

if ruleset_id != expected_id:
    raise SystemExit(
        f"Ruleset id mismatch: expected {expected_id}, got {ruleset_id!r}"
    )
if source_type != "Repository":
    raise SystemExit("selected Ruleset must be repository-owned")
if (
    not isinstance(source, str)
    or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", source) is None
):
    raise SystemExit("selected Ruleset has invalid source")
source_owner, source_name = source.split("/", 1)
if source_owner in {".", ".."} or source_name in {".", ".."}:
    raise SystemExit("selected Ruleset has unsafe source")
if source.casefold() != expected_repository.casefold():
    raise SystemExit(
        f"Ruleset source mismatch: expected {expected_repository!r}, got {source!r}"
    )
if target != "branch":
    raise SystemExit("selected Ruleset must target branches")

conditions = document.get("conditions")
ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
include = ref_name.get("include") if isinstance(ref_name, dict) else None
if not isinstance(include, list) or not all(isinstance(value, str) for value in include):
    raise SystemExit("selected Ruleset has invalid ref_name.include")

accepted_targets = {"~DEFAULT_BRANCH", f"refs/heads/{default_branch}"}
if not accepted_targets.intersection(include):
    raise SystemExit("selected Ruleset does not currently target the repository default branch")

print(f"{ruleset_id}\t{source.casefold()}\t{target}")
PY
}

initial_repository_json="${temp_root}/repository-before.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${initial_repository_json}"; then
  echo "Failed to resolve repository identity before Ruleset update." >&2
  exit 4
fi
if ! initial_repository_identity="$(repository_identity "${initial_repository_json}")"; then
  echo "Repository identity failed validation before Ruleset update." >&2
  exit 4
fi
IFS=$'\t' read -r _ _ initial_default_branch <<<"${initial_repository_identity}"

initial_ruleset_json="${temp_root}/ruleset-before.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}/rulesets/${ruleset_id}?includes_parents=false" >"${initial_ruleset_json}"; then
  echo "Failed to read selected Ruleset before update." >&2
  exit 4
fi
if ! initial_ruleset_identity="$(
  ruleset_identity "${initial_ruleset_json}" "${initial_default_branch}"
)"; then
  echo "Selected Ruleset identity failed validation before update." >&2
  exit 4
fi

put_json="${temp_root}/ruleset-put.json"
if ! gh api "${api_headers[@]}" --method PUT "repos/${repository}/rulesets/${ruleset_id}" --input "${desired_ruleset}" >"${put_json}"; then
  echo "Failed to apply Solo default-branch Ruleset." >&2
  exit 5
fi

final_repository_json="${temp_root}/repository-after.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}" >"${final_repository_json}"; then
  echo "Failed to re-read repository after Ruleset update." >&2
  exit 6
fi
if ! final_repository_identity="$(repository_identity "${final_repository_json}")"; then
  echo "Repository identity failed validation after Ruleset update." >&2
  exit 6
fi
if [[ "${initial_repository_identity}" != "${final_repository_identity}" ]]; then
  echo "Repository identity changed during Ruleset update." >&2
  exit 6
fi
IFS=$'\t' read -r _ _ final_default_branch <<<"${final_repository_identity}"

final_ruleset_json="${temp_root}/ruleset-after.json"
if ! gh api "${api_headers[@]}" --method GET "repos/${repository}/rulesets/${ruleset_id}?includes_parents=false" >"${final_ruleset_json}"; then
  echo "Failed to re-read selected Ruleset after update." >&2
  exit 6
fi
if ! final_ruleset_identity="$(
  ruleset_identity "${final_ruleset_json}" "${final_default_branch}"
)"; then
  echo "Selected Ruleset identity failed validation after update." >&2
  exit 6
fi
if [[ "${initial_ruleset_identity}" != "${final_ruleset_identity}" ]]; then
  echo "Ruleset identity changed during update." >&2
  exit 6
fi

if ! python3 "${live_validator}" "${final_ruleset_json}" "${repository}" >/dev/null; then
  echo "Ruleset update did not converge to the checked-in Solo contract." >&2
  exit 6
fi

printf 'main Ruleset %s applied and verified for %s\n' "${ruleset_id}" "${repository}"
