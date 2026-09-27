#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_TAG:?SOURCE_TAG is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"
: "${PUBLISHER_SHA:?PUBLISHER_SHA is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

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
if [[ ! "${GITHUB_REPOSITORY}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "GITHUB_REPOSITORY must be in owner/repo form." >&2
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
if document.get("ref") != expected_ref:
    raise SystemExit(
        f"GitHub Git ref identity mismatch: expected {expected_ref!r}, "
        f"got {document.get('ref')!r}"
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
  if [[ -z "${seen_tag_objects%:*}" ]]; then
    expected_outer_tag="${SOURCE_TAG}"
  fi
  parsed="$(printf '%s' "${tag_json}" | parse_tag_object "${current_tag_object_sha}" "${expected_outer_tag}")" || exit 1
  object_type="$(printf '%s\n' "${parsed}" | sed -n '1p')"
  object_sha="$(printf '%s\n' "${parsed}" | sed -n '2p')"
done

if [[ -z "${resolved_sha}" ]]; then
  echo "Release tag exceeded the maximum annotated-tag dereference depth." >&2
  exit 1
fi
if [[ "${resolved_sha}" != "${SOURCE_SHA}" ]]; then
  echo "Resolved release tag SHA ${resolved_sha} does not match source SHA ${SOURCE_SHA}." >&2
  exit 1
fi

if ! git merge-base --is-ancestor "${SOURCE_SHA}" "${PUBLISHER_SHA}"; then
  echo "Release source ${SOURCE_SHA} is not reachable from trusted publisher/default-branch commit ${PUBLISHER_SHA}." >&2
  exit 1
fi

printf '%s\n' "${resolved_sha}"
