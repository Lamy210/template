#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOLVER="${REPO_ROOT}/scripts/ci/resolve-trusted-main-artifact.sh"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

STUB_BIN="${TEMP_ROOT}/bin"
mkdir -p "${STUB_BIN}"
cat >"${STUB_BIN}/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

scenario="${GH_STUB_SCENARIO:?GH_STUB_SCENARIO is required}"
args="$*"

if [[ "${args}" == *"/actions/workflows/visual-regression.yml/runs"* ]]; then
  case "${scenario}" in
    success|wrong-artifact|expired|traversal)
      cat <<'JSON'
{"workflow_runs":[{"id":9001,"head_branch":"main","event":"push","conclusion":"success"}]}
JSON
      ;;
    pr)
      cat <<'JSON'
{"workflow_runs":[{"id":9002,"head_branch":"main","event":"pull_request","conclusion":"success"}]}
JSON
      ;;
    non-main)
      cat <<'JSON'
{"workflow_runs":[{"id":9003,"head_branch":"feature","event":"push","conclusion":"success"}]}
JSON
      ;;
    failure)
      cat <<'JSON'
{"workflow_runs":[{"id":9004,"head_branch":"main","event":"push","conclusion":"failure"}]}
JSON
      ;;
    *)
      printf '{"workflow_runs":[]}'
      ;;
  esac
  exit 0
fi

if [[ "${args}" == *"/actions/runs/9001/artifacts"* ]]; then
  case "${scenario}" in
    success|traversal)
      cat <<'JSON'
{"artifacts":[{"id":7001,"name":"visual-baseline-test","expired":false}]}
JSON
      ;;
    wrong-artifact)
      cat <<'JSON'
{"artifacts":[{"id":7002,"name":"different-artifact","expired":false}]}
JSON
      ;;
    expired)
      cat <<'JSON'
{"artifacts":[{"id":7003,"name":"visual-baseline-test","expired":true}]}
JSON
      ;;
  esac
  exit 0
fi

if [[ "${args}" == *"/actions/artifacts/7001/zip"* ]]; then
  python3 - "${scenario}" <<'PY'
import io
import sys
import zipfile

scenario = sys.argv[1]
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    if scenario == "traversal":
        archive.writestr("../evil.txt", "escape")
    else:
        archive.writestr("profile.json", '{"profile":"test"}')
        archive.writestr("screen.png", "png-placeholder")
sys.stdout.buffer.write(buffer.getvalue())
PY
  exit 0
fi

printf 'unexpected gh invocation: %s\n' "${args}" >&2
exit 2
STUB
chmod +x "${STUB_BIN}/gh"

run_resolver() {
  local scenario="$1"
  local output_dir="$2"
  PATH="${STUB_BIN}:${PATH}" \
    GH_STUB_SCENARIO="${scenario}" \
    GH_TOKEN="test-token" \
    "${RESOLVER}" \
      --repository Lamy210/template \
      --workflow visual-regression.yml \
      --artifact visual-baseline-test \
      --output "${output_dir}"
}

assert_status() {
  local scenario="$1"
  local expected_status="$2"
  local output_dir="${TEMP_ROOT}/out-${scenario}"
  local stdout_file="${TEMP_ROOT}/${scenario}.stdout"
  local stderr_file="${TEMP_ROOT}/${scenario}.stderr"

  set +e
  run_resolver "${scenario}" "${output_dir}" >"${stdout_file}" 2>"${stderr_file}"
  local status=$?
  set -e

  if [[ "${status}" -ne "${expected_status}" ]]; then
    printf 'scenario %s: expected exit %s, got %s\n' "${scenario}" "${expected_status}" "${status}" >&2
    cat "${stderr_file}" >&2 || true
    return 1
  fi
}

success_output="${TEMP_ROOT}/success"
run_id="$(run_resolver success "${success_output}")"
[[ "${run_id}" == "9001" ]]
[[ -f "${success_output}/profile.json" ]]
[[ -f "${success_output}/screen.png" ]]

assert_status pr 4
assert_status non-main 4
assert_status failure 4
assert_status wrong-artifact 4
assert_status expired 4

traversal_output="${TEMP_ROOT}/traversal"
set +e
run_resolver traversal "${traversal_output}" >/dev/null 2>"${TEMP_ROOT}/traversal.stderr"
traversal_status=$?
set -e
[[ "${traversal_status}" -ne 0 ]]
[[ ! -e "${TEMP_ROOT}/evil.txt" ]]

printf 'trusted-main artifact resolver tests passed\n'
