#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOLVER="${REPO_ROOT}/scripts/release/resolve-release-build-artifact.sh"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

STUB_BIN="${TEMP_ROOT}/bin"
mkdir -p "${STUB_BIN}"
cat >"${STUB_BIN}/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

scenario="${GH_STUB_SCENARIO:?GH_STUB_SCENARIO is required}"
args="$*"
sha="0123456789abcdef0123456789abcdef01234567"
repository_id=1367784801
if [[ "${scenario}" == "boolean-repository-id" ]]; then
  repository_id=true
fi

emit_zip() {
  python3 - "${scenario}" <<'PY'
import io
import sys
import zipfile

scenario = sys.argv[1]
buffer = io.BytesIO()


def add_file(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


with zipfile.ZipFile(buffer, "w") as archive:
    if scenario == "traversal":
        add_file(archive, "../escape", b"bad")
    add_file(archive, "release-input/unsigned-macos-app.tar.gz", b"archive-fixture")
    add_file(archive, "release-input/build-provenance.json", b"{}")
sys.stdout.buffer.write(buffer.getvalue())
PY
}

emit_digest() {
  emit_zip | python3 -c 'import hashlib,sys; print("sha256:" + hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

if [[ "${args}" == "api repos/Lamy210/template" ]]; then
  printf '{"id":%s,"full_name":"Lamy210/template"}' "${repository_id}"
  exit 0
fi

if [[ "${args}" == *"/actions/workflows/release-build.yml"* ]]; then
  if [[ "${scenario}" == "malformed-workflow" ]]; then
    printf '{not-json'
  elif [[ "${scenario}" == "boolean-workflow-id" ]]; then
    printf '{"id":true,"name":"Release Build","path":".github/workflows/release-build.yml"}'
  else
    printf '{"id":4242,"name":"Release Build","path":".github/workflows/release-build.yml"}'
  fi
  exit 0
fi

if [[ "${args}" == *"/actions/runs/9001"* && "${args}" != *"/artifacts"* ]]; then
  workflow_id=4242
  path='.github/workflows/release-build.yml'
  attempt=2
  event='push'
  conclusion='success'
  repo='Lamy210/template'
  head_repository_id="${repository_id}"
  run_repository_id="${repository_id}"
  case "${scenario}" in
    boolean-workflow-id) workflow_id=true ;;
    boolean-run-attempt) attempt=true ;;
    wrong-workflow) workflow_id=9999 ;;
    wrong-path) path='.github/workflows/other.yml' ;;
    wrong-attempt) attempt=3 ;;
    wrong-event) event='workflow_dispatch' ;;
    failed-run) conclusion='failure' ;;
    wrong-repo) repo='attacker/template' ;;
    wrong-head-repo-id) head_repository_id=9999 ;;
    wrong-run-repo-id) run_repository_id=9999 ;;
  esac
  printf '{"id":9001,"run_attempt":%s,"event":"%s","conclusion":"%s","head_sha":"%s","workflow_id":%s,"path":"%s","head_repository":{"id":%s,"full_name":"%s"},"repository":{"id":%s,"full_name":"Lamy210/template"}}' \
    "${attempt}" "${event}" "${conclusion}" "${sha}" "${workflow_id}" "${path}" \
    "${head_repository_id}" "${repo}" "${run_repository_id}"
  exit 0
fi

if [[ "${args}" == *"/actions/runs/9001/artifacts"* ]]; then
  digest="$(emit_digest)"
  if [[ "${scenario}" == "paginated" ]]; then
    if [[ "${args}" == *"page=2"* ]]; then
      printf '{"total_count":101,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}"
    else
      printf '{"total_count":101,"artifacts":[{"id":6999,"name":"decoy","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}"
    fi
    exit 0
  fi
  case "${scenario}" in
    boolean-run-attempt)
      printf '{"total_count":1,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-1","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}"
      ;;
    boolean-artifact-id)
      printf '{"total_count":1,"artifacts":[{"id":true,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}"
      ;;
    expired)
      printf '{"total_count":1,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":true,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}"
      ;;
    duplicate)
      printf '{"total_count":2,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}},{"id":7002,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}" "${digest}" "${sha}"
      ;;
    wrong-artifact)
      printf '{"total_count":1,"artifacts":[{"id":7001,"name":"other","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}"
      ;;
    missing-digest)
      printf '{"total_count":1,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":false,"workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${sha}"
      ;;
    digest-mismatch)
      printf '{"total_count":1,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"sha256:%064d","workflow_run":{"id":9001,"head_sha":"%s"}}]}' 0 "${sha}"
      ;;
    artifact-wrong-run)
      printf '{"total_count":1,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"%s","workflow_run":{"id":9999,"head_sha":"%s"}}]}' "${digest}" "${sha}"
      ;;
    *)
      printf '{"total_count":1,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"%s","workflow_run":{"id":9001,"head_sha":"%s"}}]}' "${digest}" "${sha}"
      ;;
  esac
  exit 0
fi

if [[ "${args}" == *"/actions/artifacts/7001/zip"* || ( "${scenario}" == "boolean-artifact-id" && "${args}" == *"/actions/artifacts/True/zip"* ) ]]; then
  emit_zip
  exit 0
fi

printf 'unexpected gh invocation: %s\n' "${args}" >&2
exit 2
STUB
chmod +x "${STUB_BIN}/gh"

run_resolver() {
  local scenario="$1"
  local output_dir="$2"
  local run_attempt="${3:-2}"
  PATH="${STUB_BIN}:${PATH}" \
    GH_STUB_SCENARIO="${scenario}" \
    GH_TOKEN="test-token" \
    bash "${RESOLVER}" \
    --repository Lamy210/template \
    --workflow-path .github/workflows/release-build.yml \
    --run-id 9001 \
    --run-attempt "${run_attempt}" \
    --output "${output_dir}"
}

assert_status() {
  local scenario="$1"
  local expected_status="$2"
  local run_attempt="${3:-2}"
  local output_dir="${TEMP_ROOT}/out-${scenario}"
  set +e
  run_resolver "${scenario}" "${output_dir}" "${run_attempt}" >"${TEMP_ROOT}/${scenario}.stdout" 2>"${TEMP_ROOT}/${scenario}.stderr"
  local status=$?
  set -e
  if [[ "${status}" -ne "${expected_status}" ]]; then
    printf 'scenario %s: expected exit %s, got %s\n' "${scenario}" "${expected_status}" "${status}" >&2
    cat "${TEMP_ROOT}/${scenario}.stderr" >&2 || true
    return 1
  fi
}

success_output="${TEMP_ROOT}/success"
run_resolver success "${success_output}"
[[ -f "${success_output}/release-input/unsigned-macos-app.tar.gz" ]]
[[ -f "${success_output}/release-input/build-provenance.json" ]]
[[ -f "${success_output}/source-artifact-metadata.json" ]]
python3 - "${success_output}/source-artifact-metadata.json" <<'PY'
import json
import re
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    metadata = json.load(handle)
assert metadata["repository"] == "Lamy210/template"
assert metadata["workflowId"] == 4242
assert metadata["workflowPath"] == ".github/workflows/release-build.yml"
assert metadata["runId"] == 9001
assert metadata["runAttempt"] == 2
assert metadata["sourceSHA"] == "0123456789abcdef0123456789abcdef01234567"
assert metadata["artifactId"] == 7001
assert metadata["artifactName"] == "unsigned-macos-release-9001-2"
assert re.fullmatch(r"sha256:[0-9a-f]{64}", metadata["artifactDigest"])
PY

paginated_output="${TEMP_ROOT}/paginated"
run_resolver paginated "${paginated_output}"
[[ -f "${paginated_output}/release-input/unsigned-macos-app.tar.gz" ]]
[[ -f "${paginated_output}/source-artifact-metadata.json" ]]

assert_status wrong-workflow 4
assert_status wrong-path 4
assert_status wrong-attempt 4
assert_status wrong-event 4
assert_status failed-run 4
assert_status wrong-repo 4
assert_status wrong-head-repo-id 4
assert_status wrong-run-repo-id 4
assert_status boolean-repository-id 3
assert_status boolean-workflow-id 3
assert_status boolean-artifact-id 3
assert_status boolean-run-attempt 3 1
assert_status expired 4
assert_status wrong-artifact 4
assert_status duplicate 3
assert_status malformed-workflow 3
assert_status missing-digest 6
assert_status digest-mismatch 6
assert_status artifact-wrong-run 4
assert_status traversal 5

[[ ! -e "${TEMP_ROOT}/escape" ]]
printf 'release build artifact resolver tests passed\n'
