#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_TAG:?SOURCE_TAG is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"
: "${PUBLISHER_SHA:?PUBLISHER_SHA is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

if [[ ! "${SOURCE_TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
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

parse_object() {
  python3 -c '
import json
import re
import sys
try:
    document = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError) as error:
    raise SystemExit(f"invalid GitHub Git object JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("GitHub Git object response must be an object")
obj = document.get("object")
if not isinstance(obj, dict):
    raise SystemExit("GitHub Git object response is missing object metadata")
object_type = obj.get("type")
object_sha = obj.get("sha")
if object_type not in {"commit", "tag"}:
    raise SystemExit(f"unsupported GitHub Git object type: {object_type!r}")
if not isinstance(object_sha, str) or re.fullmatch(r"[0-9a-f]{40}", object_sha) is None:
    raise SystemExit("GitHub Git object SHA is invalid")
print(object_type)
print(object_sha)
'
}

ref_json="$(gh api --method GET "/repos/${GITHUB_REPOSITORY}/git/ref/tags/${SOURCE_TAG}")" || {
  echo "Failed to resolve release tag through GitHub API: ${SOURCE_TAG}" >&2
  exit 1
}
parsed="$(printf '%s' "${ref_json}" | parse_object)" || exit 1
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

  tag_json="$(gh api --method GET "/repos/${GITHUB_REPOSITORY}/git/tags/${object_sha}")" || {
    echo "Failed to dereference annotated release tag object: ${object_sha}" >&2
    exit 1
  }
  parsed="$(printf '%s' "${tag_json}" | parse_object)" || exit 1
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
