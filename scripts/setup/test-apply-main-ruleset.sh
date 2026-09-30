#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="${repo_root}/scripts/setup/apply-main-ruleset.sh"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/apply-main-ruleset-test.XXXXXX")"
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
phase=before
[[ -f "${GH_FAKE_STATE}" ]] && phase=after

if [[ "${args}" == *"--method GET repos/Example/Repo"* &&
      "${args}" != *"/rulesets/"* ]]; then
  repository_id=123
  full_name="Example/Repo"
  default_branch="main"
  if [[ "${scenario}" == "identity-mismatch" && "${phase}" == before ]]; then
    full_name="Example/Other"
  fi
  if [[ "${scenario}" == "identity-drift" && "${phase}" == after ]]; then
    repository_id=124
  fi
  printf '{"id":%s,"full_name":"%s","default_branch":"%s"}\n'     "${repository_id}" "${full_name}" "${default_branch}"
  exit 0
fi

if [[ "${args}" == *"--method GET repos/Example/Repo/rulesets/42?includes_parents=false"* ]]; then
  ruleset_id=42
  source="Example/Repo"
  target="branch"

  if [[ "${scenario}" == "wrong-ruleset-source" && "${phase}" == before ]]; then
    source="Example/Other"
  fi
  if [[ "${scenario}" == "wrong-ruleset-target" && "${phase}" == before ]]; then
    target="tag"
  fi
  if [[ "${scenario}" == "ruleset-id-mismatch" && "${phase}" == before ]]; then
    ruleset_id=43
  fi

  if [[ "${phase}" == before ]]; then
    printf '{"id":%s,"name":"main","target":"%s","source_type":"Repository","source":"%s","enforcement":"active","bypass_actors":[],"current_user_can_bypass":"never","conditions":{"ref_name":{"include":["~DEFAULT_BRANCH","refs/heads/release**"],"exclude":[]}},"rules":[{"type":"deletion"},{"type":"non_fast_forward"},{"type":"pull_request","parameters":{"required_approving_review_count":0,"dismiss_stale_reviews_on_push":true,"require_code_owner_review":false,"require_last_push_approval":false,"required_review_thread_resolution":false,"allowed_merge_methods":["merge","squash","rebase"]}}]}\n'       "${ruleset_id}" "${target}" "${source}"
    exit 0
  fi

  if [[ "${scenario}" == "nonconvergent" ]]; then
    printf '{"id":42,"name":"Solo default branch","target":"branch","source_type":"Repository","source":"Example/Repo","enforcement":"active","bypass_actors":[],"current_user_can_bypass":"never","conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},"rules":[{"type":"deletion"},{"type":"non_fast_forward"},{"type":"required_linear_history"},{"type":"pull_request","parameters":{"allowed_merge_methods":["squash"],"dismiss_stale_reviews_on_push":true,"require_code_owner_review":false,"require_last_push_approval":false,"required_approving_review_count":0,"required_review_thread_resolution":true}}]}\n'
    exit 0
  fi

  printf '{"id":42,"name":"Solo default branch","target":"branch","source_type":"Repository","source":"Example/Repo","enforcement":"active","bypass_actors":[],"current_user_can_bypass":"never","conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},"rules":[{"type":"deletion"},{"type":"non_fast_forward"},{"type":"required_linear_history"},{"type":"pull_request","parameters":{"allowed_merge_methods":["squash"],"dismiss_stale_reviews_on_push":true,"require_code_owner_review":false,"require_last_push_approval":false,"required_approving_review_count":0,"required_review_thread_resolution":true}},{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"Required gate"},{"context":"Tests / Required Gate"},{"context":"swift-quality / Swift quality"}],"strict_required_status_checks_policy":true}}]}\n'
  exit 0
fi

if [[ "${args}" == *"--method PUT repos/Example/Repo/rulesets/42"* ]]; then
  if [[ "${scenario}" == "put-fails" ]]; then
    exit 91
  fi

  input_path=""
  previous=""
  for argument in "$@"; do
    if [[ "${previous}" == "--input" ]]; then
      input_path="${argument}"
      break
    fi
    previous="${argument}"
  done
  [[ -n "${input_path}" && -f "${input_path}" ]] || {
    echo "Ruleset PUT did not receive an input file." >&2
    exit 92
  }

  grep -F '"name": "Solo default branch"' "${input_path}" >/dev/null
  grep -F '"context": "Required gate"' "${input_path}" >/dev/null
  grep -F '"context": "Tests / Required Gate"' "${input_path}" >/dev/null
  grep -F '"context": "swift-quality / Swift quality"' "${input_path}" >/dev/null

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
  PATH="${fake_bin}:${PATH}"     GH_FAKE_SCENARIO="${scenario}"     GH_FAKE_LOG="${log}"     GH_FAKE_STATE="${state}"     bash "${script}"     --repository Example/Repo     --confirm-repository Example/Repo     --ruleset-id 42     --confirm-ruleset-id 42     --apply
}

: >"${temp_root}/no-apply-gh.log"
if PATH="${fake_bin}:${PATH}" GH_FAKE_LOG="${temp_root}/no-apply-gh.log" GH_FAKE_STATE="${temp_root}/unused"   bash "${script}"   --repository Example/Repo   --confirm-repository Example/Repo   --ruleset-id 42   --confirm-ruleset-id 42 >"${temp_root}/no-apply.out" 2>"${temp_root}/no-apply.err"; then
  echo "Ruleset helper accepted a mutation request without --apply." >&2
  exit 1
fi
grep -F -- "--apply is required" "${temp_root}/no-apply.err" >/dev/null
[[ ! -s "${temp_root}/no-apply-gh.log" ]] || {
  echo "Ruleset helper contacted GitHub before --apply validation." >&2
  exit 1
}

: >"${temp_root}/confirm-repo-gh.log"
if PATH="${fake_bin}:${PATH}" GH_FAKE_LOG="${temp_root}/confirm-repo-gh.log" GH_FAKE_STATE="${temp_root}/unused2"   bash "${script}"   --repository Example/Repo   --confirm-repository Example/Other   --ruleset-id 42   --confirm-ruleset-id 42   --apply >"${temp_root}/confirm-repo.out" 2>"${temp_root}/confirm-repo.err"; then
  echo "Ruleset helper accepted mismatched repository confirmation." >&2
  exit 1
fi
grep -F -- "--confirm-repository must exactly equal" "${temp_root}/confirm-repo.err" >/dev/null
[[ ! -s "${temp_root}/confirm-repo-gh.log" ]] || {
  echo "Ruleset helper contacted GitHub before repository confirmation." >&2
  exit 1
}

: >"${temp_root}/confirm-ruleset-gh.log"
if PATH="${fake_bin}:${PATH}" GH_FAKE_LOG="${temp_root}/confirm-ruleset-gh.log" GH_FAKE_STATE="${temp_root}/unused3"   bash "${script}"   --repository Example/Repo   --confirm-repository Example/Repo   --ruleset-id 42   --confirm-ruleset-id 43   --apply >"${temp_root}/confirm-ruleset.out" 2>"${temp_root}/confirm-ruleset.err"; then
  echo "Ruleset helper accepted mismatched Ruleset confirmation." >&2
  exit 1
fi
grep -F -- "--confirm-ruleset-id must exactly equal" "${temp_root}/confirm-ruleset.err" >/dev/null
[[ ! -s "${temp_root}/confirm-ruleset-gh.log" ]] || {
  echo "Ruleset helper contacted GitHub before Ruleset confirmation." >&2
  exit 1
}

success_output="$(run_apply success)"
[[ "${success_output}" == "main Ruleset 42 applied and verified for Example/Repo" ]]
[[ "$(grep -Fc -- "--method PUT repos/Example/Repo/rulesets/42" "${temp_root}/gh-success.log")" -eq 1 ]]
[[ "$(grep -Fc -- "--method GET repos/Example/Repo/rulesets/42?includes_parents=false" "${temp_root}/gh-success.log")" -eq 2 ]]
[[ "$(grep -Fc -- "--method GET repos/Example/Repo" "${temp_root}/gh-success.log")" -eq 4 ]]

for scenario in identity-mismatch wrong-ruleset-source wrong-ruleset-target ruleset-id-mismatch; do
  if run_apply "${scenario}" >"${temp_root}/${scenario}.out" 2>"${temp_root}/${scenario}.err"; then
    echo "Ruleset helper accepted unsafe precondition scenario: ${scenario}" >&2
    exit 1
  fi
  if grep -F -- "--method PUT" "${temp_root}/gh-${scenario}.log" >/dev/null; then
    echo "Ruleset helper mutated GitHub after failed precondition: ${scenario}" >&2
    exit 1
  fi
done

if run_apply put-fails >"${temp_root}/put-fails.out" 2>"${temp_root}/put-fails.err"; then
  echo "Ruleset helper accepted a failed Ruleset PUT." >&2
  exit 1
fi
grep -F "Failed to apply Solo default-branch Ruleset." "${temp_root}/put-fails.err" >/dev/null

if run_apply identity-drift >"${temp_root}/identity-drift.out" 2>"${temp_root}/identity-drift.err"; then
  echo "Ruleset helper accepted repository identity drift." >&2
  exit 1
fi
grep -F "Repository identity changed during Ruleset update." "${temp_root}/identity-drift.err" >/dev/null

if run_apply nonconvergent >"${temp_root}/nonconvergent.out" 2>"${temp_root}/nonconvergent.err"; then
  echo "Ruleset helper accepted a nonconvergent Ruleset update." >&2
  exit 1
fi
grep -F "Ruleset update did not converge to the checked-in Solo contract." "${temp_root}/nonconvergent.err" >/dev/null

printf 'apply-main-ruleset tests passed\n'
