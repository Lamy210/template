#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/shell-repository-entrypoints.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

fake_bin="${temp_root}/bin"
call_log="${temp_root}/gh-calls.log"
mkdir -p "${fake_bin}"

cat >"${fake_bin}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${GH_CALL_LOG:?}"
exit 97
FAKE_GH
chmod 0755 "${fake_bin}/gh"

export PATH="${fake_bin}:${PATH}"
export GH_CALL_LOG="${call_log}"
export GH_TOKEN="test-token"

unsafe="../escape"
sha_a="0123456789abcdef0123456789abcdef01234567"
sha_b="1123456789abcdef0123456789abcdef01234567"

assert_rejected_before_gh() {
  local label="$1"
  local expected_status="$2"
  shift 2

  : >"${call_log}"
  set +e
  "$@" >"${temp_root}/stdout" 2>"${temp_root}/stderr"
  local status="$?"
  set -e

  if [[ "${status}" != "${expected_status}" ]]; then
    echo "${label}: expected exit ${expected_status}, got ${status}" >&2
    cat "${temp_root}/stderr" >&2
    exit 1
  fi
  if [[ -s "${call_log}" ]]; then
    echo "${label}: contacted GitHub before rejecting unsafe repository name" >&2
    cat "${call_log}" >&2
    exit 1
  fi
}

assert_rejected_before_gh   "release source verifier" 1   env     SOURCE_TAG=v1.2.3     SOURCE_SHA="${sha_a}"     PUBLISHER_SHA="${sha_b}"     GITHUB_REPOSITORY="${unsafe}"     EXPECTED_REPOSITORY_ID=1     GH_TOKEN="${GH_TOKEN}"     bash "${repo_root}/scripts/release/verify-release-source.sh"

assert_rejected_before_gh   "release build artifact resolver" 2   bash "${repo_root}/scripts/release/resolve-release-build-artifact.sh"     --repository "${unsafe}"     --workflow-path .github/workflows/release-build.yml     --run-id 1     --run-attempt 1     --output "${temp_root}/release-build-output"

assert_rejected_before_gh   "source artifact repository verifier" 2   bash "${repo_root}/scripts/release/verify-source-artifact-repository.sh"     --repository "${unsafe}"     --repository-id 1     --source-metadata "${temp_root}/missing-source-metadata.json"

assert_rejected_before_gh   "post-split ancestor proof" 2   bash "${repo_root}/scripts/release/prove-post-split-ancestor-runtime.sh"     --repository "${unsafe}"     --confirm-disposable "${unsafe}"     --source-ref main     --tag v0.0.1

assert_rejected_before_gh   "release environment proof" 2   bash "${repo_root}/scripts/release/prove-release-environment-policy.sh"     --repository "${unsafe}"     --confirm-disposable "${unsafe}"

assert_rejected_before_gh   "post-split runtime audit" 2   bash "${repo_root}/scripts/release/audit-post-split-runtime-proof.sh"     "${unsafe}" 1 2

assert_rejected_before_gh   "trusted main artifact resolver" 2   bash "${repo_root}/scripts/ci/resolve-trusted-main-artifact.sh"     --repository "${unsafe}"     --workflow tests.yml     --artifact fixture     --output "${temp_root}/trusted-artifact-output"

assert_rejected_before_gh   "release-tag immutability proof" 2   bash "${repo_root}/scripts/ci/prove-release-tag-immutability.sh"     --repository "${unsafe}"     --confirm-disposable "${unsafe}"     --tag v0.0.1     --initial-sha "${sha_a}"     --move-sha "${sha_b}"

printf 'shell repository entrypoint validation regressions passed\n'
