#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="${repo_root}/scripts/setup/apply-repository-merge-settings.sh"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/apply-repository-merge-settings-test.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

fake_bin="${temp_root}/bin"
mkdir -p "${fake_bin}"
cat >"${fake_bin}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail

: "${GH_FAKE_LOG:?GH_FAKE_LOG is required}"
: "${GH_FAKE_STATE:?GH_FAKE_STATE is required}"
printf '%s\n' "$*" >>"${GH_FAKE_LOG}"

scenario="${GH_FAKE_SCENARIO:-success}"
args="$*"

if [[ "${args}" == *"--method GET repos/Example/Repo"* ]]; then
  phase=before
  if [[ -f "${GH_FAKE_STATE}" ]]; then
    phase=after
  fi

  repository_id=123
  full_name="Example/Repo"
  allow_squash=true
  allow_merge=true
  allow_rebase=true
  delete_branch=false

  if [[ "${scenario}" == "identity-mismatch" && "${phase}" == before ]]; then
    full_name="Example/Other"
  fi
  if [[ "${phase}" == after ]]; then
    allow_merge=false
    allow_rebase=false
    delete_branch=true
    if [[ "${scenario}" == "identity-drift" ]]; then
      repository_id=124
    fi
    if [[ "${scenario}" == "nonconvergent" ]]; then
      allow_rebase=true
    fi
  fi

  printf '{"id":%s,"full_name":"%s","allow_squash_merge":%s,"allow_merge_commit":%s,"allow_rebase_merge":%s,"delete_branch_on_merge":%s}\n' \
    "${repository_id}" "${full_name}" "${allow_squash}" "${allow_merge}" "${allow_rebase}" "${delete_branch}"
  exit 0
fi

if [[ "${args}" == *"--method PATCH repos/Example/Repo"* ]]; then
  if [[ "${scenario}" == "patch-fails" ]]; then
    exit 91
  fi
  expected=(
    "-F allow_squash_merge=true"
    "-F allow_merge_commit=false"
    "-F allow_rebase_merge=false"
    "-F delete_branch_on_merge=true"
  )
  for field in "${expected[@]}"; do
    if [[ " ${args} " != *" ${field} "* ]]; then
      echo "Missing expected PATCH field: ${field}" >&2
      exit 92
    fi
  done
  : >"${GH_FAKE_STATE}"
  printf '{"updated":true}\n'
  exit 0
fi

echo "Unexpected gh command: ${args}" >&2
exit 97
FAKE_GH
chmod 0755 "${fake_bin}/gh"

run_apply() {
  local scenario="$1"
  local log="${temp_root}/gh-${scenario}.log"
  local state="${temp_root}/state-${scenario}"
  PATH="${fake_bin}:${PATH}" \
    GH_FAKE_SCENARIO="${scenario}" \
    GH_FAKE_LOG="${log}" \
    GH_FAKE_STATE="${state}" \
    bash "${script}" \
    --repository Example/Repo \
    --confirm-repository Example/Repo \
    --apply
}

: >"${temp_root}/no-gh.log"
if PATH="${fake_bin}:${PATH}" GH_FAKE_LOG="${temp_root}/no-gh.log" GH_FAKE_STATE="${temp_root}/unused" \
  bash "${script}" --repository Example/Repo --confirm-repository Example/Repo >"${temp_root}/no-apply.out" 2>"${temp_root}/no-apply.err"; then
  echo "Apply helper accepted a mutation request without --apply." >&2
  exit 1
fi
grep -F -- "--apply is required" "${temp_root}/no-apply.err" >/dev/null
[[ ! -s "${temp_root}/no-gh.log" ]] || {
  echo "Apply helper contacted GitHub before --apply validation." >&2
  exit 1
}

: >"${temp_root}/confirm-gh.log"
if PATH="${fake_bin}:${PATH}" GH_FAKE_LOG="${temp_root}/confirm-gh.log" GH_FAKE_STATE="${temp_root}/unused2" \
  bash "${script}" --repository Example/Repo --confirm-repository Example/Other --apply >"${temp_root}/confirm.out" 2>"${temp_root}/confirm.err"; then
  echo "Apply helper accepted mismatched repository confirmation." >&2
  exit 1
fi
grep -F -- "--confirm-repository must exactly equal" "${temp_root}/confirm.err" >/dev/null
[[ ! -s "${temp_root}/confirm-gh.log" ]] || {
  echo "Apply helper contacted GitHub before confirmation validation." >&2
  exit 1
}

success_output="$(run_apply success)"
[[ "${success_output}" == "repository merge settings applied and verified for Example/Repo" ]]
grep -F -- "--method PATCH repos/Example/Repo" "${temp_root}/gh-success.log" >/dev/null
[[ "$(grep -Fc -- "--method GET repos/Example/Repo" "${temp_root}/gh-success.log")" -eq 2 ]]
[[ "$(grep -Fc -- "--method PATCH repos/Example/Repo" "${temp_root}/gh-success.log")" -eq 1 ]]

if run_apply identity-mismatch >"${temp_root}/identity-mismatch.out" 2>"${temp_root}/identity-mismatch.err"; then
  echo "Apply helper accepted the wrong initial repository identity." >&2
  exit 1
fi
if grep -F -- "--method PATCH" "${temp_root}/gh-identity-mismatch.log" >/dev/null; then
  echo "Apply helper mutated repository after initial identity mismatch." >&2
  exit 1
fi

if run_apply patch-fails >"${temp_root}/patch-fails.out" 2>"${temp_root}/patch-fails.err"; then
  echo "Apply helper accepted a failed repository PATCH." >&2
  exit 1
fi
grep -F "Failed to apply repository merge-policy settings." "${temp_root}/patch-fails.err" >/dev/null

if run_apply identity-drift >"${temp_root}/identity-drift.out" 2>"${temp_root}/identity-drift.err"; then
  echo "Apply helper accepted repository replacement during update." >&2
  exit 1
fi
grep -F "Repository identity changed during merge-policy update." "${temp_root}/identity-drift.err" >/dev/null

if run_apply nonconvergent >"${temp_root}/nonconvergent.out" 2>"${temp_root}/nonconvergent.err"; then
  echo "Apply helper accepted a non-convergent merge-policy update." >&2
  exit 1
fi
grep -F "did not converge to the template contract" "${temp_root}/nonconvergent.err" >/dev/null

printf 'repository merge settings apply-helper regressions passed\n'
