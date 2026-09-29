#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
doctor="${repo_root}/scripts/ci/audit-live-repository-merge-settings.sh"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/repository-merge-settings-test.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

fake_bin="${temp_root}/bin"
mkdir -p "${fake_bin}"
cat >"${fake_bin}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail

: "${GH_FAKE_LOG:?GH_FAKE_LOG is required}"
: "${GH_FAKE_COUNT_FILE:?GH_FAKE_COUNT_FILE is required}"
printf '%s
' "$*" >>"${GH_FAKE_LOG}"

if [[ "$*" != *"--method GET repos/Lamy210/template"* ]]; then
  echo "Unexpected gh command: $*" >&2
  exit 97
fi

count=0
if [[ -f "${GH_FAKE_COUNT_FILE}" ]]; then
  count="$(cat "${GH_FAKE_COUNT_FILE}")"
fi
count="$((count + 1))"
printf '%s
' "${count}" >"${GH_FAKE_COUNT_FILE}"

repository_id=1367784801
allow_squash=true
allow_merge=false
allow_rebase=false
delete_branch=true

case "${GH_FAKE_SCENARIO:-success}" in
  success)
    ;;
  policy-drift)
    allow_merge=true
    ;;
  identity-drift)
    if [[ "${count}" -ge 2 ]]; then
      repository_id=1367784802
    fi
    ;;
  *)
    echo "Unknown scenario: ${GH_FAKE_SCENARIO}" >&2
    exit 98
    ;;
esac

printf '{"id":%s,"full_name":"Lamy210/template","allow_squash_merge":%s,"allow_merge_commit":%s,"allow_rebase_merge":%s,"delete_branch_on_merge":%s}
'   "${repository_id}" "${allow_squash}" "${allow_merge}" "${allow_rebase}" "${delete_branch}"
FAKE_GH
chmod 0755 "${fake_bin}/gh"

run_doctor() {
  local scenario="$1"
  local count_file="${temp_root}/count-${scenario}"
  local log_file="${temp_root}/gh-${scenario}.log"
  PATH="${fake_bin}:${PATH}"     GH_FAKE_SCENARIO="${scenario}"     GH_FAKE_COUNT_FILE="${count_file}"     GH_FAKE_LOG="${log_file}"     bash "${doctor}" Lamy210/template
}

success_output="$(run_doctor success)"
if [[ "${success_output}" != "repository merge settings match the template policy for Lamy210/template" ]]; then
  echo "Unexpected success output: ${success_output}" >&2
  exit 1
fi
if [[ "$(wc -l <"${temp_root}/gh-success.log" | tr -d ' ')" != 2 ]]; then
  echo "Successful doctor did not re-read repository state exactly once." >&2
  exit 1
fi
if grep -E -- '--method (POST|PUT|PATCH|DELETE)' "${temp_root}/gh-success.log" >/dev/null; then
  echo "Repository merge settings doctor attempted a mutation." >&2
  exit 1
fi

if run_doctor policy-drift >"${temp_root}/drift.out" 2>"${temp_root}/drift.err"; then
  echo "Repository merge settings doctor accepted merge-policy drift." >&2
  exit 1
fi
grep -F "allow_merge_commit must equal false" "${temp_root}/drift.err" >/dev/null
grep -F "do not match the template policy" "${temp_root}/drift.err" >/dev/null

if run_doctor identity-drift >"${temp_root}/identity.out" 2>"${temp_root}/identity.err"; then
  echo "Repository merge settings doctor accepted identity drift." >&2
  exit 1
fi
grep -F "Repository identity or merge settings changed during the audit." "${temp_root}/identity.err" >/dev/null

if PATH="${fake_bin}:${PATH}" bash "${doctor}" ../escape >"${temp_root}/unsafe.out" 2>"${temp_root}/unsafe.err"; then
  echo "Repository merge settings doctor accepted an unsafe repository name." >&2
  exit 1
fi
grep -F "canonical owner/repo" "${temp_root}/unsafe.err" >/dev/null

printf 'repository merge settings live-doctor regressions passed
'
