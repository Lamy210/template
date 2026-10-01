#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="${repo_root}/scripts/setup/reconcile-solo-governance.sh"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/reconcile-solo-governance-test.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

fake_bin="${temp_root}/bin"
mkdir -p "${fake_bin}"
cat >"${fake_bin}/bash" <<'FAKE_BASH'
#!/usr/bin/env bash
set -euo pipefail

: "${RECONCILE_FAKE_LOG:?RECONCILE_FAKE_LOG is required}"
scenario="${RECONCILE_SCENARIO:-success}"
target="${1:-}"
shift || true
printf '%s\t%s\n' "${target}" "$*" >>"${RECONCILE_FAKE_LOG}"

case "${target}" in
  */scripts/setup/apply-repository-merge-settings.sh)
    [[ " $* " == *" --repository Example/Repo "* ]]
    [[ " $* " == *" --confirm-repository Example/Repo "* ]]
    [[ " $* " == *" --apply "* ]]
    if [[ "${scenario}" == "merge-fails" ]]; then
      exit 11
    fi
    printf 'repository merge settings applied and verified for Example/Repo\n'
    ;;
  */scripts/setup/apply-main-ruleset.sh)
    [[ " $* " == *" --repository Example/Repo "* ]]
    [[ " $* " == *" --confirm-repository Example/Repo "* ]]
    [[ " $* " == *" --ruleset-id 42 "* ]]
    [[ " $* " == *" --confirm-ruleset-id 42 "* ]]
    [[ " $* " == *" --apply "* ]]
    if [[ "${scenario}" == "ruleset-fails" ]]; then
      exit 12
    fi
    printf 'main Ruleset 42 applied and effective rules verified for Example/Repo\n'
    ;;
  */scripts/template/doctor.sh)
    [[ " $* " == *" --repository Example/Repo "* ]]
    [[ " $* " == *" --profile core "* ]]
    if [[ "${scenario}" == "doctor-fails" ]]; then
      exit 13
    fi
    printf 'template doctor: 4/4 checks passed for Example/Repo (profile=core)\n'
    ;;
  *)
    echo "Unexpected child bash target: ${target}" >&2
    exit 97
    ;;
esac
FAKE_BASH
chmod 0755 "${fake_bin}/bash"

run_reconcile() {
  local scenario="$1"
  local log="${temp_root}/${scenario}.log"
  PATH="${fake_bin}:${PATH}" \
    RECONCILE_SCENARIO="${scenario}" \
    RECONCILE_FAKE_LOG="${log}" \
    /bin/bash "${script}" \
    --repository Example/Repo \
    --confirm-repository Example/Repo \
    --ruleset-id 42 \
    --confirm-ruleset-id 42 \
    --apply
}

: >"${temp_root}/prevalidation.log"
if PATH="${fake_bin}:${PATH}" RECONCILE_FAKE_LOG="${temp_root}/prevalidation.log" \
  /bin/bash "${script}" \
  --repository Example/Repo \
  --confirm-repository Example/Other \
  --ruleset-id 42 \
  --confirm-ruleset-id 42 \
  --apply >"${temp_root}/prevalidation.out" 2>"${temp_root}/prevalidation.err"; then
  echo "Reconciliation accepted mismatched repository confirmation." >&2
  exit 1
fi
grep -F -- "--confirm-repository must exactly equal" "${temp_root}/prevalidation.err" >/dev/null
[[ ! -s "${temp_root}/prevalidation.log" ]] || {
  echo "Reconciliation invoked child helpers before repository confirmation." >&2
  exit 1
}

: >"${temp_root}/no-apply.log"
if PATH="${fake_bin}:${PATH}" RECONCILE_FAKE_LOG="${temp_root}/no-apply.log" \
  /bin/bash "${script}" \
  --repository Example/Repo \
  --confirm-repository Example/Repo \
  --ruleset-id 42 \
  --confirm-ruleset-id 42 >"${temp_root}/no-apply.out" 2>"${temp_root}/no-apply.err"; then
  echo "Reconciliation accepted mutation without --apply." >&2
  exit 1
fi
grep -F -- "--apply is required" "${temp_root}/no-apply.err" >/dev/null
[[ ! -s "${temp_root}/no-apply.log" ]] || {
  echo "Reconciliation invoked child helpers before --apply validation." >&2
  exit 1
}

success_output="$(run_reconcile success)"
grep -F "[PASS] Repository merge settings" <<<"${success_output}" >/dev/null
grep -F "[PASS] Solo default-branch Ruleset" <<<"${success_output}" >/dev/null
grep -F "[PASS] Core governance doctor" <<<"${success_output}" >/dev/null
grep -F "merge=PASS ruleset=PASS doctor=PASS repository=Example/Repo" <<<"${success_output}" >/dev/null
[[ "$(wc -l <"${temp_root}/success.log" | tr -d ' ')" -eq 3 ]]

for scenario in merge-fails ruleset-fails doctor-fails; do
  if run_reconcile "${scenario}" >"${temp_root}/${scenario}.out" 2>"${temp_root}/${scenario}.err"; then
    echo "Reconciliation accepted failing scenario: ${scenario}" >&2
    exit 1
  fi
  [[ "$(wc -l <"${temp_root}/${scenario}.log" | tr -d ' ')" -eq 3 ]] || {
    echo "Reconciliation did not run all components for scenario: ${scenario}" >&2
    exit 1
  }
  grep -F "repository=Example/Repo" "${temp_root}/${scenario}.out" >/dev/null
done

grep -F "merge=FAIL ruleset=PASS doctor=PASS" "${temp_root}/merge-fails.out" >/dev/null
grep -F "merge=PASS ruleset=FAIL doctor=PASS" "${temp_root}/ruleset-fails.out" >/dev/null
grep -F "merge=PASS ruleset=PASS doctor=FAIL" "${temp_root}/doctor-fails.out" >/dev/null

printf 'solo governance reconciliation tests passed\n'
