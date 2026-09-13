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
    malformed-runs)
      printf '{not-json'
      ;;
    success|wrong-artifact|expired|duplicate-artifact|absolute|traversal|duplicate-member|symlink-escape)
      cat <<'JSON'
{"workflow_runs":[{"id":9001,"run_attempt":2,"head_sha":"0123456789abcdef0123456789abcdef01234567","head_branch":"main","event":"push","conclusion":"success","head_repository":{"full_name":"Lamy210/template"}}]}
JSON
      ;;
    wrong-repo)
      cat <<'JSON'
{"workflow_runs":[{"id":9005,"run_attempt":1,"head_sha":"1123456789abcdef0123456789abcdef01234567","head_branch":"main","event":"push","conclusion":"success","head_repository":{"full_name":"attacker/template"}}]}
JSON
      ;;
    pr)
      cat <<'JSON'
{"workflow_runs":[{"id":9002,"run_attempt":1,"head_sha":"2123456789abcdef0123456789abcdef01234567","head_branch":"main","event":"pull_request","conclusion":"success","head_repository":{"full_name":"Lamy210/template"}}]}
JSON
      ;;
    non-main)
      cat <<'JSON'
{"workflow_runs":[{"id":9003,"run_attempt":1,"head_sha":"3123456789abcdef0123456789abcdef01234567","head_branch":"feature","event":"push","conclusion":"success","head_repository":{"full_name":"Lamy210/template"}}]}
JSON
      ;;
    failure)
      cat <<'JSON'
{"workflow_runs":[{"id":9004,"run_attempt":1,"head_sha":"4123456789abcdef0123456789abcdef01234567","head_branch":"main","event":"push","conclusion":"failure","head_repository":{"full_name":"Lamy210/template"}}]}
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
    success|absolute|traversal|duplicate-member|symlink-escape)
      cat <<'JSON'
{"artifacts":[{"id":7001,"name":"visual-baseline-test","expired":false,"digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}
JSON
      ;;
    wrong-artifact)
      cat <<'JSON'
{"artifacts":[{"id":7002,"name":"different-artifact","expired":false,"digest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}]}
JSON
      ;;
    expired)
      cat <<'JSON'
{"artifacts":[{"id":7003,"name":"visual-baseline-test","expired":true,"digest":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}]}
JSON
      ;;
    duplicate-artifact)
      cat <<'JSON'
{"artifacts":[{"id":7001,"name":"visual-baseline-test","expired":false},{"id":7004,"name":"visual-baseline-test","expired":false}]}
JSON
      ;;
  esac
  exit 0
fi

if [[ "${args}" == *"/actions/artifacts/7001/zip"* ]]; then
  python3 - "${scenario}" <<'PY'
import io
import stat
import sys
import zipfile

scenario = sys.argv[1]
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    if scenario == "absolute":
        archive.writestr("/tmp/evil.txt", "escape")
    elif scenario == "traversal":
        archive.writestr("../evil.txt", "escape")
    elif scenario == "duplicate-member":
        archive.writestr("images/screen.png", "first")
        archive.writestr("images/./screen.png", "second")
    elif scenario == "symlink-escape":
        link = zipfile.ZipInfo("images/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../outside")
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
    bash "${RESOLVER}" \
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
[[ -f "${success_output}/resolver-metadata.json" ]]
python3 - "${success_output}/resolver-metadata.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    metadata = json.load(handle)

assert metadata["repository"] == "Lamy210/template"
assert metadata["workflow"] == "visual-regression.yml"
assert metadata["runId"] == 9001
assert metadata["runAttempt"] == 2
assert metadata["sourceSHA"] == "0123456789abcdef0123456789abcdef01234567"
assert metadata["artifactId"] == 7001
assert metadata["artifactName"] == "visual-baseline-test"
assert metadata["artifactDigest"] == "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PY

assert_status empty 4
assert_status pr 4
assert_status non-main 4
assert_status failure 4
assert_status wrong-repo 4
assert_status wrong-artifact 4
assert_status expired 4
assert_status malformed-runs 3
assert_status duplicate-artifact 3
assert_status absolute 5
assert_status traversal 5
assert_status duplicate-member 5
assert_status symlink-escape 5

[[ ! -e "${TEMP_ROOT}/evil.txt" ]]
[[ ! -e "${TEMP_ROOT}/outside" ]]

printf 'trusted-main artifact resolver tests passed\n'
