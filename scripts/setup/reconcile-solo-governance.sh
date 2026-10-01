#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  reconcile-solo-governance.sh \
    --repository owner/repo \
    --confirm-repository owner/repo \
    --ruleset-id 123456 \
    --confirm-ruleset-id 123456 \
    --apply

Applies the Solo governance repository settings through the existing guarded
helpers, then always runs the read-only core doctor.

This command is not transactional. One mutation can succeed while another
fails. The final doctor exposes any remaining drift and the command exits
non-zero unless every mutation and the doctor succeed.
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
  echo "--apply is required because this command mutates repository governance settings." >&2
  exit 2
fi

command -v bash >/dev/null 2>&1 || {
  echo "bash is required." >&2
  exit 2
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
merge_helper="${repo_root}/scripts/setup/apply-repository-merge-settings.sh"
ruleset_helper="${repo_root}/scripts/setup/apply-main-ruleset.sh"
doctor="${repo_root}/scripts/template/doctor.sh"

for required_file in "${merge_helper}" "${ruleset_helper}" "${doctor}"; do
  if [[ ! -f "${required_file}" || -L "${required_file}" ]]; then
    echo "Required governance helper is unavailable or is a symlink: ${required_file}" >&2
    exit 2
  fi
done

merge_status=0
ruleset_status=0
doctor_status=0

printf '==> Repository merge settings\n'
if bash "${merge_helper}" \
  --repository "${repository}" \
  --confirm-repository "${confirmed_repository}" \
  --apply; then
  printf '[PASS] Repository merge settings\n'
else
  merge_status="$?"
  printf '[FAIL] Repository merge settings (exit %s)\n' "${merge_status}" >&2
fi

printf '==> Solo default-branch Ruleset\n'
if bash "${ruleset_helper}" \
  --repository "${repository}" \
  --confirm-repository "${confirmed_repository}" \
  --ruleset-id "${ruleset_id}" \
  --confirm-ruleset-id "${confirmed_ruleset_id}" \
  --apply; then
  printf '[PASS] Solo default-branch Ruleset\n'
else
  ruleset_status="$?"
  printf '[FAIL] Solo default-branch Ruleset (exit %s)\n' "${ruleset_status}" >&2
fi

printf '==> Core governance doctor\n'
if bash "${doctor}" --repository "${repository}" --profile core; then
  printf '[PASS] Core governance doctor\n'
else
  doctor_status="$?"
  printf '[FAIL] Core governance doctor (exit %s)\n' "${doctor_status}" >&2
fi

printf 'solo governance reconciliation: merge=%s ruleset=%s doctor=%s repository=%s\n' \
  "$([[ "${merge_status}" -eq 0 ]] && printf PASS || printf FAIL)" \
  "$([[ "${ruleset_status}" -eq 0 ]] && printf PASS || printf FAIL)" \
  "$([[ "${doctor_status}" -eq 0 ]] && printf PASS || printf FAIL)" \
  "${repository}"

if ((merge_status != 0 || ruleset_status != 0 || doctor_status != 0)); then
  exit 1
fi
