#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common/repository-name.sh
source "${script_dir}/repository-name.sh"

valid=(
  "owner/repo"
  "Lamy210/template"
  "example/homebrew-tap"
  "owner.name/repo_name"
)

invalid=(
  ""
  "repo"
  "/repo"
  "owner/"
  "owner/repo/extra"
  "../escape"
  "./repo"
  "owner/.."
  "owner/."
  'owner\repo'
)

for repository in "${valid[@]}"; do
  if ! is_canonical_repository_name "${repository}"; then
    echo "canonical repository name was rejected: ${repository}" >&2
    exit 1
  fi
done

for repository in "${invalid[@]}"; do
  if is_canonical_repository_name "${repository}"; then
    echo "unsafe repository name was accepted: ${repository}" >&2
    exit 1
  fi
done

if is_canonical_repository_name owner/repo extra; then
  echo "repository validator accepted multiple arguments" >&2
  exit 1
fi

printf 'shell repository-name validation regressions passed\n'
