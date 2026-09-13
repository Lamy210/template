#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOLVER="${REPO_ROOT}/scripts/ci/resolve-trusted-main-artifact.sh"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

STUB_BIN="${TEMP_ROOT}/bin"
STUB_LOG="${TEMP_ROOT}/gh.log"
mkdir -p "${STUB_BIN}"

cat >"${STUB_BIN}/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

: "${GH_STUB_LOG:?GH_STUB_LOG is required}"
printf '%s\n' "$*" >>"${GH_STUB_LOG}"

args="$*"
if [[ "${args}" == *"/actions/workflows/visual-regression.yml/runs"* ]]; then
  cat <<'JSON'
{"workflow_runs":[{"id":9100,"run_attempt":1,"head_sha":"0123456789abcdef0123456789abcdef01234567","head_branch":"release/1.x","event":"push","conclusion":"success","head_repository":{"full_name":"Lamy210/template"}}]}
JSON
  exit 0
fi

if [[ "${args}" == *"/actions/runs/9100/artifacts"* ]]; then
  printf '{"artifacts":[]}'
  exit 0
fi

printf 'unexpected gh invocation: %s\n' "${args}" >&2
exit 2
STUB
chmod +x "${STUB_BIN}/gh"

run_custom_branch() {
  PATH="${STUB_BIN}:${PATH}" \
    GH_STUB_LOG="${STUB_LOG}" \
    GH_TOKEN="test-token" \
    bash "${RESOLVER}" \
    --repository Lamy210/template \
    --workflow visual-regression.yml \
    --artifact visual-baseline-test \
    --output "${TEMP_ROOT}/output" \
    --branch 'release/1.x' \
    --max-runs 73
}

set +e
run_custom_branch >"${TEMP_ROOT}/stdout" 2>"${TEMP_ROOT}/stderr"
status=$?
set -e

if [[ "${status}" -ne 4 ]]; then
  printf 'expected no-artifact exit 4 for custom branch, got %s\n' "${status}" >&2
  cat "${TEMP_ROOT}/stderr" >&2 || true
  exit 1
fi

grep -F 'branch=release%2F1.x&event=push&status=success&per_page=73' "${STUB_LOG}" >/dev/null
grep -F 'actions/runs/9100/artifacts' "${STUB_LOG}" >/dev/null

assert_usage_error() {
  local value="$1"
  set +e
  PATH="${STUB_BIN}:${PATH}" \
    GH_STUB_LOG="${STUB_LOG}" \
    GH_TOKEN="test-token" \
    bash "${RESOLVER}" \
    --repository Lamy210/template \
    --workflow visual-regression.yml \
    --artifact visual-baseline-test \
    --output "${TEMP_ROOT}/invalid-${value}" \
    --max-runs "${value}" >/dev/null 2>&1
  local actual=$?
  set -e
  if [[ "${actual}" -ne 2 ]]; then
    printf 'expected usage exit 2 for --max-runs %s, got %s\n' "${value}" "${actual}" >&2
    exit 1
  fi
}

assert_usage_error 0
assert_usage_error 101
assert_usage_error nope

printf 'trusted artifact resolver option tests passed\n'
