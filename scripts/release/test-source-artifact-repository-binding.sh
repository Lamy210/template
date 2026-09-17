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
artifact_repository_id="${repository_id}"
artifact_head_repository_id="${repository_id}"
case "${scenario}" in
  artifact-wrong-repository-id) artifact_repository_id=9999 ;;
  artifact-wrong-head-repository-id) artifact_head_repository_id=9999 ;;
esac

if [[ "${args}" == "api repos/Lamy210/template" ]]; then
  printf '{"id":%s,"full_name":"Lamy210/template"}' "${repository_id}"
  exit 0
fi

if [[ "${args}" == *"/actions/workflows/release-build.yml"* ]]; then
  printf '{"id":4242,"name":"Release Build","path":".github/workflows/release-build.yml"}'
  exit 0
fi

if [[ "${args}" == *"/actions/runs/9001"* && "${args}" != *"/artifacts"* ]]; then
  printf '{"id":9001,"run_attempt":2,"event":"push","conclusion":"success","head_sha":"%s","workflow_id":4242,"path":".github/workflows/release-build.yml","head_repository":{"id":%s,"full_name":"Lamy210/template"},"repository":{"id":%s,"full_name":"Lamy210/template"}}' \
    "${sha}" "${repository_id}" "${repository_id}"
  exit 0
fi

if [[ "${args}" == *"/actions/runs/9001/artifacts"* ]]; then
  printf '{"total_count":1,"artifacts":[{"id":7001,"name":"unsigned-macos-release-9001-2","expired":false,"digest":"sha256:%064d","workflow_run":{"id":9001,"head_sha":"%s","repository_id":%s,"head_repository_id":%s}}]}' \
    0 "${sha}" "${artifact_repository_id}" "${artifact_head_repository_id}"
  exit 0
fi

if [[ "${args}" == *"/actions/artifacts/7001/zip"* ]]; then
  printf 'x'
  exit 0
fi

printf 'unexpected gh invocation: %s\n' "${args}" >&2
exit 2
STUB
chmod +x "${STUB_BIN}/gh"

assert_rejected() {
  local scenario="$1"
  local output_dir="${TEMP_ROOT}/out-${scenario}"
  set +e
  PATH="${STUB_BIN}:${PATH}" \
    GH_STUB_SCENARIO="${scenario}" \
    GH_TOKEN="test-token" \
    bash "${RESOLVER}" \
      --repository Lamy210/template \
      --workflow-path .github/workflows/release-build.yml \
      --run-id 9001 \
      --run-attempt 2 \
      --output "${output_dir}" \
      >"${TEMP_ROOT}/${scenario}.stdout" \
      2>"${TEMP_ROOT}/${scenario}.stderr"
  local status=$?
  set -e
  if [[ "${status}" -ne 4 ]]; then
    printf 'scenario %s: expected trust rejection exit 4, got %s\n' "${scenario}" "${status}" >&2
    cat "${TEMP_ROOT}/${scenario}.stderr" >&2 || true
    return 1
  fi
}

assert_rejected artifact-wrong-repository-id
assert_rejected artifact-wrong-head-repository-id
printf 'source artifact repository binding tests passed\n'
