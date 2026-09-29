#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common/repository-name.sh
source "${script_dir}/../common/repository-name.sh"

: "${SOURCE_TAG:?SOURCE_TAG is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"
: "${PUBLISHER_SHA:?PUBLISHER_SHA is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${EXPECTED_REPOSITORY_ID:?EXPECTED_REPOSITORY_ID is required}"

if [[ ! "${SOURCE_TAG}" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "SOURCE_TAG must match stable SemVer vX.Y.Z: ${SOURCE_TAG}" >&2
  exit 1
fi
if [[ ! "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SOURCE_SHA must be 40 lowercase hexadecimal characters." >&2
  exit 1
fi
if [[ ! "${PUBLISHER_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "PUBLISHER_SHA must be 40 lowercase hexadecimal characters." >&2
  exit 1
fi
if ! is_canonical_repository_name "${GITHUB_REPOSITORY}"; then
  echo "GITHUB_REPOSITORY must use canonical owner/repo form." >&2
  exit 1
fi
if [[ ! "${EXPECTED_REPOSITORY_ID}" =~ ^[0-9]+$ ]]; then
  echo "EXPECTED_REPOSITORY_ID must be a positive integer." >&2
  exit 1
fi
EXPECTED_REPOSITORY_ID="$((10#${EXPECTED_REPOSITORY_ID}))"
if ((EXPECTED_REPOSITORY_ID <= 0)); then
  echo "EXPECTED_REPOSITORY_ID must be positive." >&2
  exit 1
fi

command -v git >/dev/null 2>&1 || {
  echo "git is required." >&2
  exit 1
}
command -v gh >/dev/null 2>&1 || {
  echo "gh is required." >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required." >&2
  exit 1
}

git cat-file -e "${PUBLISHER_SHA}^{commit}" 2>/dev/null || {
  echo "Trusted publisher commit is unavailable locally: ${PUBLISHER_SHA}" >&2
  exit 1
}
git cat-file -e "${SOURCE_SHA}^{commit}" 2>/dev/null || {
  echo "Release source commit is unavailable in trusted publisher history checkout: ${SOURCE_SHA}" >&2
  exit 1
}

repository_identity() {
  local response
  if ! response="$(gh api "repos/${GITHUB_REPOSITORY}")"; then
    echo "Failed to resolve source repository identity." >&2
    return 1
  fi

  python3 - "${GITHUB_REPOSITORY}" "${EXPECTED_REPOSITORY_ID}" "${response}" <<'PY'
import json
import re
import sys

expected_name, expected_id_text, response = sys.argv[1:]
expected_id = int(expected_id_text)

try:
    document = json.loads(response)
except json.JSONDecodeError as error:
    raise SystemExit(f"source repository identity response is invalid JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("source repository identity response must be an object")

repository_id = document.get("id")
full_name = document.get("full_name")
if type(repository_id) is not int or repository_id <= 0:
    raise SystemExit("source repository identity response has no positive integer id")
if (
    not isinstance(full_name, str)
    or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) is None
):
    raise SystemExit("source repository identity response has no canonical full_name")
if repository_id != expected_id:
    raise SystemExit(
        f"source repository id mismatch: expected {expected_id}, got {repository_id}"
    )
if full_name.casefold() != expected_name.casefold():
    raise SystemExit(
        f"source repository full_name mismatch: expected {expected_name!r}, got {full_name!r}"
    )

print(repository_id)
print(full_name.casefold())
PY
}

if ! initial_repository_identity="$(repository_identity)"; then
  echo "Unable to bind source repository identity before release-tag verification." >&2
  exit 1
fi

parse_ref_object() {
  python3 -c '
import json
import re
import sys

expected_ref = sys.argv[1]
try:
    document = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError) as error:
    raise SystemExit(f"invalid GitHub Git ref JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("GitHub Git ref response must be an object")
actual_ref = document.get("ref")
if actual_ref != expected_ref:
    raise SystemExit(
        f"GitHub Git ref identity mismatch: expected {expected_ref!r}, "
        f"got {actual_ref!r}"
    )
obj = document.get("object")
if not isinstance(obj, dict):
    raise SystemExit("GitHub Git ref response is missing object metadata")
object_type = obj.get("type")
object_sha = obj.get("sha")
if object_type not in {"commit", "tag"}:
    raise SystemExit(f"unsupported GitHub Git ref object type: {object_type!r}")
if not isinstance(object_sha, str) or re.fullmatch(r"[0-9a-f]{40}", object_sha) is None:
    raise SystemExit("GitHub Git ref object SHA is invalid")
print(object_type)
print(object_sha)
' "$1"
}

parse_tag_object() {
  python3 -c '
import json
import re
import sys

expected_sha, expected_outer_tag = sys.argv[1:]
try:
    document = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError) as error:
    raise SystemExit(f"invalid GitHub annotated tag JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("GitHub annotated tag response must be an object")

tag_sha = document.get("sha")
tag_name = document.get("tag")
if not isinstance(tag_sha, str) or re.fullmatch(r"[0-9a-f]{40}", tag_sha) is None:
    raise SystemExit("GitHub annotated tag object SHA is invalid")
if tag_sha != expected_sha:
    raise SystemExit(
        f"GitHub annotated tag object identity mismatch: expected {expected_sha}, "
        f"got {tag_sha}"
    )
if (
    not isinstance(tag_name, str)
    or not tag_name
    or "\n" in tag_name
    or "\r" in tag_name
):
    raise SystemExit("GitHub annotated tag name must be a non-empty single-line string")
if expected_outer_tag and tag_name != expected_outer_tag:
    raise SystemExit(
        f"outer annotated release tag name mismatch: expected {expected_outer_tag!r}, "
        f"got {tag_name!r}"
    )

obj = document.get("object")
if not isinstance(obj, dict):
    raise SystemExit("GitHub annotated tag response is missing target metadata")
object_type = obj.get("type")
object_sha = obj.get("sha")
if object_type not in {"commit", "tag"}:
    raise SystemExit(f"unsupported GitHub annotated tag target type: {object_type!r}")
if not isinstance(object_sha, str) or re.fullmatch(r"[0-9a-f]{40}", object_sha) is None:
    raise SystemExit("GitHub annotated tag target SHA is invalid")
print(object_type)
print(object_sha)
' "$1" "$2"
}

ref_json="$(gh api --method GET "/repos/${GITHUB_REPOSITORY}/git/ref/tags/${SOURCE_TAG}")" || {
  echo "Failed to resolve release tag through GitHub API: ${SOURCE_TAG}" >&2
  exit 1
}
parsed="$(printf '%s' "${ref_json}" | parse_ref_object "refs/tags/${SOURCE_TAG}")" || exit 1
object_type="$(printf '%s\n' "${parsed}" | sed -n '1p')"
object_sha="$(printf '%s\n' "${parsed}" | sed -n '2p')"

resolved_sha=""
seen_tag_objects=""
tag_depth=0
for _ in 1 2 3 4 5 6 7 8; do
  if [[ "${object_type}" == commit ]]; then
    resolved_sha="${object_sha}"
    break
  fi

  case ":${seen_tag_objects}:" in
    *":${object_sha}:"*)
      echo "Annotated release tag contains a cycle at ${object_sha}." >&2
      exit 1
      ;;
  esac
  seen_tag_objects="${seen_tag_objects:+${seen_tag_objects}:}${object_sha}"

  current_tag_object_sha="${object_sha}"
  tag_json="$(gh api --method GET "/repos/${GITHUB_REPOSITORY}/git/tags/${current_tag_object_sha}")" || {
    echo "Failed to dereference annotated release tag object: ${current_tag_object_sha}" >&2
    exit 1
  }

  expected_outer_tag=""
  if ((tag_depth == 0)); then
    expected_outer_tag="${SOURCE_TAG}"
  fi
  parsed="$(printf '%s' "${tag_json}" | parse_tag_object "${current_tag_object_sha}" "${expected_outer_tag}")" || exit 1
  object_type="$(printf '%s\n' "${parsed}" | sed -n '1p')"
  object_sha="$(printf '%s\n' "${parsed}" | sed -n '2p')"
  tag_depth=$((tag_depth + 1))
done

if [[ -z "${resolved_sha}" ]]; then
  echo "Release tag exceeded the maximum annotated-tag dereference depth." >&2
  exit 1
fi
if [[ "${resolved_sha}" != "${SOURCE_SHA}" ]]; then
  echo "Resolved release tag SHA ${resolved_sha} does not match source SHA ${SOURCE_SHA}." >&2
  exit 1
fi

if ! final_repository_identity="$(repository_identity)"; then
  echo "Unable to rebind source repository identity after release-tag verification." >&2
  exit 1
fi
if [[ "${final_repository_identity}" != "${initial_repository_identity}" ]]; then
  echo "Source repository identity changed during release-tag verification." >&2
  exit 1
fi

if ! git merge-base --is-ancestor "${SOURCE_SHA}" "${PUBLISHER_SHA}"; then
  echo "Release source ${SOURCE_SHA} is not reachable from trusted publisher/default-branch commit ${PUBLISHER_SHA}." >&2
  exit 1
fi

printf '%s\n' "${resolved_sha}"
