#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  doctor.sh --repository owner/repo [--profile core|release]

Profiles:
  core     Audit merge settings, the default-branch Ruleset/effective rules,
           and the immutable release-tag Ruleset.
  release  Run core plus the protected release Environment and native immutable
           releases setting. This profile needs credentials that can read those
           repository administration surfaces.

This command is read-only. It runs every selected check and reports all drift
found in one invocation.
EOF
}

repository=""
profile="core"

while (($#)); do
  case "$1" in
    --repository)
      repository="${2:-}"
      shift 2
      ;;
    --profile)
      profile="${2:-}"
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

case "${profile}" in
  core | release)
    ;;
  *)
    echo "--profile must be either core or release." >&2
    exit 2
    ;;
esac

command -v bash >/dev/null 2>&1 || {
  echo "bash is required." >&2
  exit 2
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

check_names=(
  "Repository merge settings"
  "Solo default-branch Ruleset"
  "Effective default-branch rules"
  "Immutable release-tag Ruleset"
)
check_paths=(
  "scripts/ci/audit-live-repository-merge-settings.sh"
  "scripts/ci/audit-live-main-ruleset.sh"
  "scripts/ci/audit-live-main-rules.sh"
  "scripts/ci/audit-live-release-tag-ruleset.sh"
)

if [[ "${profile}" == release ]]; then
  check_names+=(
    "Protected release Environment"
    "Native immutable releases"
  )
  check_paths+=(
    "scripts/release/audit-release-environment.sh"
    "scripts/ci/audit-live-immutable-releases.sh"
  )
fi

for relative_path in "${check_paths[@]}"; do
  full_path="${repo_root}/${relative_path}"
  if [[ ! -f "${full_path}" || -L "${full_path}" ]]; then
    echo "Template doctor check is unavailable or is a symlink: ${relative_path}" >&2
    exit 2
  fi
done

passed=0
failed=0
total="${#check_paths[@]}"

for index in "${!check_paths[@]}"; do
  name="${check_names[${index}]}"
  relative_path="${check_paths[${index}]}"
  full_path="${repo_root}/${relative_path}"

  printf '==> %s\n' "${name}"
  if bash "${full_path}" "${repository}"; then
    printf '[PASS] %s\n' "${name}"
    passed="$((passed + 1))"
  else
    status="$?"
    printf '[FAIL] %s (exit %s)\n' "${name}" "${status}" >&2
    failed="$((failed + 1))"
  fi
done

printf 'template doctor: %s/%s checks passed for %s (profile=%s)\n' \
  "${passed}" "${total}" "${repository}" "${profile}"

if ((failed > 0)); then
  exit 1
fi
