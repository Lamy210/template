#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="${repo_root}/scripts/setup/apply-main-ruleset.sh"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/apply-main-ruleset-bounded-metadata.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

fake_bin="${temp_root}/bin"
mkdir -p "${fake_bin}"
cat >"${fake_bin}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail

: "${GH_FAKE_LOG:?GH_FAKE_LOG is required}"
scenario="${GH_FAKE_SCENARIO:?GH_FAKE_SCENARIO is required}"
args="$*"
printf '%s\n' "${args}" >>"${GH_FAKE_LOG}"

append_oversized_padding() {
  python3 - <<'PY'
import sys

sys.stdout.write(" " * (2 * 1024 * 1024 + 1))
PY
}

if [[ "${args}" == *"--method GET repos/Example/Repo"* &&
  "${args}" != *"/rulesets/"* ]]; then
  printf '%s\n' '{"id":123,"full_name":"Example/Repo","default_branch":"main"}'
  if [[ "${scenario}" == "oversized-repository" ]]; then
    append_oversized_padding
  fi
  exit 0
fi

if [[ "${args}" == *"--method GET repos/Example/Repo/rulesets/42?includes_parents=false"* ]]; then
  printf '%s\n' '{"id":42,"name":"main","target":"branch","source_type":"Repository","source":"Example/Repo","enforcement":"active","bypass_actors":[],"current_user_can_bypass":"never","conditions":{"ref_name":{"include":["~DEFAULT_BRANCH","refs/heads/release**"],"exclude":[]}},"rules":[{"type":"deletion"},{"type":"non_fast_forward"},{"type":"pull_request","parameters":{"required_approving_review_count":0,"dismiss_stale_reviews_on_push":true,"require_code_owner_review":false,"require_last_push_approval":false,"required_review_thread_resolution":false,"allowed_merge_methods":["merge","squash","rebase"]}}]}'
  if [[ "${scenario}" == "oversized-ruleset" ]]; then
    append_oversized_padding
  fi
  exit 0
fi

if [[ "${args}" == *"--method PUT repos/Example/Repo/rulesets/42"* ]]; then
  exit 91
fi

echo "Unexpected gh command: ${args}" >&2
exit 97
FAKE_GH
chmod 0755 "${fake_bin}/gh"

run_case() {
  local scenario="$1"
  local log="${temp_root}/${scenario}.log"
  local state="${temp_root}/${scenario}.state"

  : >"${log}"
  PATH="${fake_bin}:${PATH}" \
    GITHUB_ACTIONS=false \
    GH_FAKE_SCENARIO="${scenario}" \
    GH_FAKE_LOG="${log}" \
    GH_FAKE_STATE="${state}" \
    bash "${script}" \
    --repository Example/Repo \
    --confirm-repository Example/Repo \
    --ruleset-id 42 \
    --confirm-ruleset-id 42 \
    --apply >"${temp_root}/${scenario}.out" 2>"${temp_root}/${scenario}.err" || true

  if grep -F -- "--method PUT repos/Example/Repo/rulesets/42" "${log}" >/dev/null; then
    echo "Ruleset helper reached PUT after accepting ${scenario} metadata." >&2
    exit 1
  fi
}

run_case oversized-repository
run_case oversized-ruleset

printf 'apply-main-ruleset bounded metadata regressions passed\n'
