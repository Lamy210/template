#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_TAG:?SOURCE_TAG is required}"
: "${SOURCE_SHA:?SOURCE_SHA is required}"
: "${PUBLISHER_SHA:?PUBLISHER_SHA is required}"

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

command -v git >/dev/null 2>&1 || {
  echo "git is required." >&2
  exit 1
}

git cat-file -e "${PUBLISHER_SHA}^{commit}" 2>/dev/null || {
  echo "Trusted publisher commit is unavailable locally: ${PUBLISHER_SHA}" >&2
  exit 1
}

remote_ref="refs/tags/${SOURCE_TAG}"
local_ref="refs/tags/${SOURCE_TAG}"
git fetch --quiet --force --no-tags origin "+${remote_ref}:${local_ref}"

resolved_sha="$(git rev-parse --verify "${local_ref}^{commit}")"
if [[ ! "${resolved_sha}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Resolved tag commit SHA is invalid: ${resolved_sha}" >&2
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
