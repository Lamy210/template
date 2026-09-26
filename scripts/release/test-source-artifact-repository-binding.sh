#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERIFIER="${REPO_ROOT}/scripts/release/verify-source-artifact-repository.sh"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

sha="0123456789abcdef0123456789abcdef01234567"
source_metadata="${TEMP_ROOT}/source-artifact-metadata.json"
printf '{"artifactId":7001,"runId":9001,"sourceSHA":"%s"}\n' "${sha}" >"${source_metadata}"

STUB_BIN="${TEMP_ROOT}/bin"
mkdir -p "${STUB_BIN}"
cat >"${STUB_BIN}/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

scenario="${GH_STUB_SCENARIO:?GH_STUB_SCENARIO is required}"
args="$*"
sha="0123456789abcdef0123456789abcdef01234567"
artifact_id=7001
run_id=9001
repository_id=1367784801
head_repository_id=1367784801
case "${scenario}" in
  wrong-artifact-id) artifact_id=7002 ;;
  wrong-run-id) run_id=9002 ;;
  wrong-sha) sha="1123456789abcdef0123456789abcdef01234567" ;;
  wrong-repository-id) repository_id=9999 ;;
  wrong-head-repository-id) head_repository_id=9999 ;;
  boolean-repository-id) repository_id=true ;;
  boolean-head-repository-id) head_repository_id=true ;;
esac

if [[ "${args}" == "api repos/Lamy210/template/actions/artifacts/7001" ]]; then
  printf '{"id":%s,"workflow_run":{"id":%s,"head_sha":"%s","repository_id":%s,"head_repository_id":%s}}' \
    "${artifact_id}" "${run_id}" "${sha}" "${repository_id}" "${head_repository_id}"
  exit 0
fi

printf 'unexpected gh invocation: %s\n' "${args}" >&2
exit 2
STUB
chmod +x "${STUB_BIN}/gh"

assert_status() {
  local scenario="$1"
  local expected_status="$2"
  set +e
  PATH="${STUB_BIN}:${PATH}" \
    GH_STUB_SCENARIO="${scenario}" \
    GH_TOKEN="test-token" \
    bash "${VERIFIER}" \
    --repository Lamy210/template \
    --repository-id 1367784801 \
    --source-metadata "${source_metadata}" \
    >"${TEMP_ROOT}/${scenario}.stdout" \
    2>"${TEMP_ROOT}/${scenario}.stderr"
  local status=$?
  set -e
  if [[ "${status}" -ne "${expected_status}" ]]; then
    printf 'scenario %s: expected exit %s, got %s\n' "${scenario}" "${expected_status}" "${status}" >&2
    cat "${TEMP_ROOT}/${scenario}.stderr" >&2 || true
    return 1
  fi
}

assert_status success 0
assert_status wrong-artifact-id 4
assert_status wrong-run-id 4
assert_status wrong-sha 4
assert_status wrong-repository-id 4
assert_status wrong-head-repository-id 4
assert_status boolean-repository-id 3
assert_status boolean-head-repository-id 3
printf 'source artifact repository binding tests passed\n'
