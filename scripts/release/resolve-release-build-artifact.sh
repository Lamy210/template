#!/usr/bin/env bash
set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_INFRA=3
readonly EXIT_REJECTED=4
readonly EXIT_UNSAFE_ARCHIVE=5
readonly EXIT_INTEGRITY=6

usage() {
  cat >&2 <<'EOF'
Usage: resolve-release-build-artifact.sh \
  --repository owner/repo \
  --workflow-path .github/workflows/release-build.yml \
  --run-id 123 \
  --run-attempt 1 \
  --output directory
EOF
}

die() {
  local status="$1"
  shift
  printf '%s\n' "$*" >&2
  exit "${status}"
}

repository=""
workflow_path=""
run_id=""
run_attempt=""
output_dir=""

while (($# > 0)); do
  case "$1" in
    --repository)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --repository'
      repository="$2"
      shift 2
      ;;
    --workflow-path)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --workflow-path'
      workflow_path="$2"
      shift 2
      ;;
    --run-id)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --run-id'
      run_id="$2"
      shift 2
      ;;
    --run-attempt)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --run-attempt'
      run_attempt="$2"
      shift 2
      ;;
    --output)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --output'
      output_dir="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage
      die "${EXIT_USAGE}" "unknown argument: $1"
      ;;
  esac
done

[[ "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "${EXIT_USAGE}" '--repository must be owner/repo'
[[ "${workflow_path}" =~ ^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$ ]] || die "${EXIT_USAGE}" '--workflow-path must be a canonical workflow path'
[[ "${run_id}" =~ ^[0-9]+$ ]] || die "${EXIT_USAGE}" '--run-id must be a positive integer'
[[ "${run_attempt}" =~ ^[0-9]+$ ]] || die "${EXIT_USAGE}" '--run-attempt must be a positive integer'
run_id_number=$((10#${run_id}))
run_attempt_number=$((10#${run_attempt}))
((run_id_number > 0)) || die "${EXIT_USAGE}" '--run-id must be positive'
((run_attempt_number > 0)) || die "${EXIT_USAGE}" '--run-attempt must be positive'
run_id="${run_id_number}"
run_attempt="${run_attempt_number}"
[[ -n "${output_dir}" ]] || die "${EXIT_USAGE}" '--output is required'
[[ ! -e "${output_dir}" ]] || die "${EXIT_USAGE}" '--output must not already exist'
[[ -n "${GH_TOKEN:-}" ]] || die "${EXIT_USAGE}" 'GH_TOKEN is required'
command -v gh >/dev/null 2>&1 || die "${EXIT_USAGE}" 'gh is required'
command -v python3 >/dev/null 2>&1 || die "${EXIT_USAGE}" 'python3 is required'

workflow_file="${workflow_path##*/}"
artifact_name="unsigned-macos-release-${run_id}-${run_attempt}"
output_parent="$(dirname "${output_dir}")"
mkdir -p "${output_parent}"
work_root="$(mktemp -d "${output_parent}/.release-build-artifact.XXXXXX")"
trap 'rm -rf "${work_root}"' EXIT

api_to_file() {
  local endpoint="$1"
  local destination="$2"
  local attempt
  for attempt in 1 2 3; do
    if gh api "${endpoint}" >"${destination}"; then
      return 0
    fi
    rm -f "${destination}"
    if ((attempt < 3)); then
      sleep "${attempt}"
    fi
  done
  return 1
}

repository_json="${work_root}/repository.json"
workflow_json="${work_root}/workflow.json"
run_json="${work_root}/run.json"
api_to_file "repos/${repository}" "${repository_json}" || die "${EXIT_INFRA}" 'failed to query canonical repository identity'
api_to_file "repos/${repository}/actions/workflows/${workflow_file}" "${workflow_json}" || die "${EXIT_INFRA}" 'failed to query canonical build workflow'
api_to_file "repos/${repository}/actions/runs/${run_id}" "${run_json}" || die "${EXIT_INFRA}" 'failed to query triggering workflow run'

identity_file="${work_root}/identity.tsv"
if python3 - "${repository_json}" "${workflow_json}" "${run_json}" "${repository}" "${workflow_path}" "${run_id}" "${run_attempt}" >"${identity_file}" <<'PY'
import json
import re
import sys

repository_path, workflow_path, run_path, expected_repo, expected_workflow_path, run_id_text, run_attempt_text = sys.argv[1:]
expected_run_id = int(run_id_text)
expected_attempt = int(run_attempt_text)

try:
    with open(repository_path, encoding="utf-8") as handle:
        canonical_repository = json.load(handle)
    with open(workflow_path, encoding="utf-8") as handle:
        workflow = json.load(handle)
    with open(run_path, encoding="utf-8") as handle:
        run = json.load(handle)
    if not isinstance(canonical_repository, dict) or not isinstance(workflow, dict) or not isinstance(run, dict):
        raise TypeError("repository, workflow, and run responses must be objects")
except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"malformed repository/workflow/run response: {error}", file=sys.stderr)
    raise SystemExit(1)

expected_repository_id = canonical_repository.get("id")
if type(expected_repository_id) is not int or expected_repository_id <= 0:
    print("canonical repository id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
if canonical_repository.get("full_name") != expected_repo:
    print("canonical repository full name does not match expected repository", file=sys.stderr)
    raise SystemExit(2)

workflow_id = workflow.get("id")
if type(workflow_id) is not int or workflow_id <= 0:
    print("canonical workflow id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
if workflow.get("path") != expected_workflow_path or workflow.get("name") != "Release Build":
    print("canonical workflow identity does not match expected path/name", file=sys.stderr)
    raise SystemExit(2)

run_id_value = run.get("id")
if type(run_id_value) is not int or run_id_value <= 0:
    print("triggering run id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)

run_attempt_value = run.get("run_attempt")
if type(run_attempt_value) is not int or run_attempt_value <= 0:
    print("triggering run attempt is missing or invalid", file=sys.stderr)
    raise SystemExit(1)

run_workflow_id = run.get("workflow_id")
if type(run_workflow_id) is not int or run_workflow_id <= 0:
    print("triggering run workflow id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)

head_repository = run.get("head_repository")
run_repository = run.get("repository")
if not isinstance(head_repository, dict) or not isinstance(run_repository, dict):
    print("triggering run repository metadata is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
head_repository_id = head_repository.get("id")
run_repository_id = run_repository.get("id")
if type(head_repository_id) is not int or head_repository_id <= 0:
    print("triggering run head repository id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
if type(run_repository_id) is not int or run_repository_id <= 0:
    print("triggering run repository id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)

checks = [
    (run_id_value == expected_run_id, "run id mismatch"),
    (run_attempt_value == expected_attempt, "run attempt mismatch"),
    (run.get("event") == "push", "triggering run event must be push"),
    (run.get("conclusion") == "success", "triggering run must have successful conclusion"),
    (run_workflow_id == workflow_id, "triggering run workflow id mismatch"),
    (run.get("path") == expected_workflow_path, "triggering run workflow path mismatch"),
    (
        head_repository_id == expected_repository_id
        and head_repository.get("full_name") == expected_repo,
        "triggering run head repository identity mismatch",
    ),
    (
        run_repository_id == expected_repository_id
        and run_repository.get("full_name") == expected_repo,
        "triggering run repository identity mismatch",
    ),
]
for condition, message in checks:
    if not condition:
        print(message, file=sys.stderr)
        raise SystemExit(2)

source_sha = run.get("head_sha")
if not isinstance(source_sha, str) or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
    print("triggering run head SHA is invalid", file=sys.stderr)
    raise SystemExit(2)

source_tag = run.get("head_branch")
if (
    not isinstance(source_tag, str)
    or re.fullmatch(
        r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)",
        source_tag,
    )
    is None
):
    print("triggering run head ref must be a canonical stable release tag", file=sys.stderr)
    raise SystemExit(2)

print(f"{workflow_id}\t{source_sha}\t{source_tag}")
PY
then
  :
else
  identity_status=$?
  if ((identity_status == 2)); then
    die "${EXIT_REJECTED}" 'triggering workflow run failed trust validation'
  fi
  die "${EXIT_INFRA}" 'repository/workflow/run response was malformed'
fi

IFS=

artifact_pages_dir="${work_root}/artifact-pages"
mkdir -p "${artifact_pages_dir}"
first_artifact_page="${artifact_pages_dir}/page-1.json"
api_to_file "repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100&page=1" "${first_artifact_page}" || die "${EXIT_INFRA}" 'failed to query triggering run artifacts'

page_count_file="${work_root}/artifact-page-count.txt"
if python3 - "${first_artifact_page}" >"${page_count_file}" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
except (OSError, json.JSONDecodeError) as error:
    print(f"malformed artifacts response: {error}", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(payload, dict):
    print("artifacts response must be an object", file=sys.stderr)
    raise SystemExit(1)
total_count = payload.get("total_count")
artifacts = payload.get("artifacts")
if type(total_count) is not int or total_count < 0:
    print("artifacts response total_count must be a non-negative integer", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(artifacts, list):
    print("artifacts response artifacts must be a list", file=sys.stderr)
    raise SystemExit(1)
print(max(1, (total_count + 99) // 100))
PY
then
  :
else
  die "${EXIT_INFRA}" 'artifacts response was malformed'
fi

read -r artifact_page_count <"${page_count_file}"
for ((page = 2; page <= artifact_page_count; page++)); do
  page_path="${artifact_pages_dir}/page-${page}.json"
  api_to_file "repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100&page=${page}" "${page_path}" || die "${EXIT_INFRA}" 'failed to query triggering run artifact page'
done

artifacts_json="${work_root}/artifacts.json"
if python3 - "${artifact_pages_dir}" "${artifact_page_count}" "${artifacts_json}" <<'PY'
import json
from pathlib import Path
import sys

pages_dir = Path(sys.argv[1])
page_count = int(sys.argv[2])
output_path = Path(sys.argv[3])
expected_total_count = None
combined = []

for page in range(1, page_count + 1):
    page_path = pages_dir / f"page-{page}.json"
    try:
        with page_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        print(f"malformed artifacts page {page}: {error}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(payload, dict):
        print(f"artifacts page {page} must be an object", file=sys.stderr)
        raise SystemExit(1)
    total_count = payload.get("total_count")
    artifacts = payload.get("artifacts")
    if type(total_count) is not int or total_count < 0:
        print(f"artifacts page {page} total_count must be a non-negative integer", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(artifacts, list):
        print(f"artifacts page {page} artifacts must be a list", file=sys.stderr)
        raise SystemExit(1)
    if expected_total_count is None:
        expected_total_count = total_count
    elif total_count != expected_total_count:
        print("artifact total_count changed while paginating", file=sys.stderr)
        raise SystemExit(1)
    combined.extend(artifacts)

with output_path.open("w", encoding="utf-8") as handle:
    json.dump(
        {"total_count": expected_total_count, "artifacts": combined},
        handle,
        sort_keys=True,
        separators=(",", ":"),
    )
    handle.write("\n")
PY
then
  :
else
  die "${EXIT_INFRA}" 'artifact pages were malformed or inconsistent'
fi

artifact_file="${work_root}/artifact.tsv"
if python3 - "${artifacts_json}" "${artifact_name}" "${run_id}" "${source_sha}" >"${artifact_file}" <<'PY'
import json
import re
import sys

path, expected_name, run_id_text, source_sha = sys.argv[1:]
expected_run_id = int(run_id_text)
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list):
        raise TypeError("artifacts must be a list")
except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"malformed artifacts response: {error}", file=sys.stderr)
    raise SystemExit(1)

named = [item for item in artifacts if isinstance(item, dict) and item.get("name") == expected_name]
active = [item for item in named if item.get("expired") is False]
if len(active) > 1:
    print("multiple non-expired artifacts have the exact expected name", file=sys.stderr)
    raise SystemExit(1)
if not active:
    print("exact non-expired release artifact was not found", file=sys.stderr)
    raise SystemExit(2)
artifact = active[0]
artifact_id = artifact.get("id")
digest = artifact.get("digest")
workflow_run = artifact.get("workflow_run")
if type(artifact_id) is not int or artifact_id <= 0:
    print("artifact id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
    print("artifact digest is missing or invalid", file=sys.stderr)
    raise SystemExit(3)
if not isinstance(workflow_run, dict):
    print("artifact workflow_run metadata is missing", file=sys.stderr)
    raise SystemExit(2)
workflow_run_id = workflow_run.get("id")
if type(workflow_run_id) is not int or workflow_run_id <= 0:
    print("artifact workflow_run id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
if workflow_run_id != expected_run_id or workflow_run.get("head_sha") != source_sha:
    print("artifact is not bound to the exact triggering run/SHA", file=sys.stderr)
    raise SystemExit(2)
print(f"{artifact_id}\t{digest}")
PY
then
  :
else
  artifact_status=$?
  case "${artifact_status}" in
    2) die "${EXIT_REJECTED}" 'release artifact failed trust validation' ;;
    3) die "${EXIT_INTEGRITY}" 'release artifact digest metadata is invalid' ;;
    *) die "${EXIT_INFRA}" 'artifacts response was malformed or ambiguous' ;;
  esac
fi

IFS=$'\t' read -r artifact_id artifact_digest <"${artifact_file}"
archive_path="${work_root}/artifact.zip"
api_to_file "repos/${repository}/actions/artifacts/${artifact_id}/zip" "${archive_path}" || die "${EXIT_INFRA}" 'failed to download exact release artifact'

actual_digest="$(
  python3 - "${archive_path}" <<'PY'
import hashlib
import sys
hasher = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        hasher.update(block)
print("sha256:" + hasher.hexdigest())
PY
)"
[[ "${actual_digest}" == "${artifact_digest}" ]] || die "${EXIT_INTEGRITY}" "artifact digest mismatch: expected ${artifact_digest}, got ${actual_digest}"

stage_dir="${work_root}/stage"
if python3 "$(dirname "${BASH_SOURCE[0]}")/validate-actions-artifact.py" --archive "${archive_path}" --output "${stage_dir}"; then
  :
else
  die "${EXIT_UNSAFE_ARCHIVE}" 'release artifact ZIP failed confinement validation'
fi

python3 - \
  "${stage_dir}/source-artifact-metadata.json" \
  "${repository}" \
  "${workflow_id}" \
  "${workflow_path}" \
  "${run_id}" \
  "${run_attempt}" \
  "${source_sha}" \
  "${source_tag}" \
  "${artifact_id}" \
  "${artifact_name}" \
  "${artifact_digest}" <<'PY'
import json
import sys
(
    output,
    repository,
    workflow_id,
    workflow_path,
    run_id,
    run_attempt,
    source_sha,
    source_tag,
    artifact_id,
    artifact_name,
    artifact_digest,
) = sys.argv[1:]
payload = {
    "schemaVersion": 1,
    "repository": repository,
    "workflowId": int(workflow_id),
    "workflowPath": workflow_path,
    "runId": int(run_id),
    "runAttempt": int(run_attempt),
    "sourceSHA": source_sha,
    "sourceTag": source_tag,
    "artifactId": int(artifact_id),
    "artifactName": artifact_name,
    "artifactDigest": artifact_digest,
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
PY

mv "${stage_dir}" "${output_dir}"
printf 'resolved release artifact run=%s attempt=%s artifact=%s\n' "${run_id}" "${run_attempt}" "${artifact_id}"
\t' read -r workflow_id source_sha source_tag <"${identity_file}"

artifact_pages_dir="${work_root}/artifact-pages"
mkdir -p "${artifact_pages_dir}"
first_artifact_page="${artifact_pages_dir}/page-1.json"
api_to_file "repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100&page=1" "${first_artifact_page}" || die "${EXIT_INFRA}" 'failed to query triggering run artifacts'

page_count_file="${work_root}/artifact-page-count.txt"
if python3 - "${first_artifact_page}" >"${page_count_file}" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
except (OSError, json.JSONDecodeError) as error:
    print(f"malformed artifacts response: {error}", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(payload, dict):
    print("artifacts response must be an object", file=sys.stderr)
    raise SystemExit(1)
total_count = payload.get("total_count")
artifacts = payload.get("artifacts")
if type(total_count) is not int or total_count < 0:
    print("artifacts response total_count must be a non-negative integer", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(artifacts, list):
    print("artifacts response artifacts must be a list", file=sys.stderr)
    raise SystemExit(1)
print(max(1, (total_count + 99) // 100))
PY
then
  :
else
  die "${EXIT_INFRA}" 'artifacts response was malformed'
fi

read -r artifact_page_count <"${page_count_file}"
for ((page = 2; page <= artifact_page_count; page++)); do
  page_path="${artifact_pages_dir}/page-${page}.json"
  api_to_file "repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100&page=${page}" "${page_path}" || die "${EXIT_INFRA}" 'failed to query triggering run artifact page'
done

artifacts_json="${work_root}/artifacts.json"
if python3 - "${artifact_pages_dir}" "${artifact_page_count}" "${artifacts_json}" <<'PY'
import json
from pathlib import Path
import sys

pages_dir = Path(sys.argv[1])
page_count = int(sys.argv[2])
output_path = Path(sys.argv[3])
expected_total_count = None
combined = []

for page in range(1, page_count + 1):
    page_path = pages_dir / f"page-{page}.json"
    try:
        with page_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        print(f"malformed artifacts page {page}: {error}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(payload, dict):
        print(f"artifacts page {page} must be an object", file=sys.stderr)
        raise SystemExit(1)
    total_count = payload.get("total_count")
    artifacts = payload.get("artifacts")
    if type(total_count) is not int or total_count < 0:
        print(f"artifacts page {page} total_count must be a non-negative integer", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(artifacts, list):
        print(f"artifacts page {page} artifacts must be a list", file=sys.stderr)
        raise SystemExit(1)
    if expected_total_count is None:
        expected_total_count = total_count
    elif total_count != expected_total_count:
        print("artifact total_count changed while paginating", file=sys.stderr)
        raise SystemExit(1)
    combined.extend(artifacts)

with output_path.open("w", encoding="utf-8") as handle:
    json.dump(
        {"total_count": expected_total_count, "artifacts": combined},
        handle,
        sort_keys=True,
        separators=(",", ":"),
    )
    handle.write("\n")
PY
then
  :
else
  die "${EXIT_INFRA}" 'artifact pages were malformed or inconsistent'
fi

artifact_file="${work_root}/artifact.tsv"
if python3 - "${artifacts_json}" "${artifact_name}" "${run_id}" "${source_sha}" >"${artifact_file}" <<'PY'
import json
import re
import sys

path, expected_name, run_id_text, source_sha = sys.argv[1:]
expected_run_id = int(run_id_text)
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list):
        raise TypeError("artifacts must be a list")
except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"malformed artifacts response: {error}", file=sys.stderr)
    raise SystemExit(1)

named = [item for item in artifacts if isinstance(item, dict) and item.get("name") == expected_name]
active = [item for item in named if item.get("expired") is False]
if len(active) > 1:
    print("multiple non-expired artifacts have the exact expected name", file=sys.stderr)
    raise SystemExit(1)
if not active:
    print("exact non-expired release artifact was not found", file=sys.stderr)
    raise SystemExit(2)
artifact = active[0]
artifact_id = artifact.get("id")
digest = artifact.get("digest")
workflow_run = artifact.get("workflow_run")
if type(artifact_id) is not int or artifact_id <= 0:
    print("artifact id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
    print("artifact digest is missing or invalid", file=sys.stderr)
    raise SystemExit(3)
if not isinstance(workflow_run, dict):
    print("artifact workflow_run metadata is missing", file=sys.stderr)
    raise SystemExit(2)
workflow_run_id = workflow_run.get("id")
if type(workflow_run_id) is not int or workflow_run_id <= 0:
    print("artifact workflow_run id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
if workflow_run_id != expected_run_id or workflow_run.get("head_sha") != source_sha:
    print("artifact is not bound to the exact triggering run/SHA", file=sys.stderr)
    raise SystemExit(2)
print(f"{artifact_id}\t{digest}")
PY
then
  :
else
  artifact_status=$?
  case "${artifact_status}" in
    2) die "${EXIT_REJECTED}" 'release artifact failed trust validation' ;;
    3) die "${EXIT_INTEGRITY}" 'release artifact digest metadata is invalid' ;;
    *) die "${EXIT_INFRA}" 'artifacts response was malformed or ambiguous' ;;
  esac
fi

IFS=$'\t' read -r artifact_id artifact_digest <"${artifact_file}"
archive_path="${work_root}/artifact.zip"
api_to_file "repos/${repository}/actions/artifacts/${artifact_id}/zip" "${archive_path}" || die "${EXIT_INFRA}" 'failed to download exact release artifact'

actual_digest="$(
  python3 - "${archive_path}" <<'PY'
import hashlib
import sys
hasher = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        hasher.update(block)
print("sha256:" + hasher.hexdigest())
PY
)"
[[ "${actual_digest}" == "${artifact_digest}" ]] || die "${EXIT_INTEGRITY}" "artifact digest mismatch: expected ${artifact_digest}, got ${actual_digest}"

stage_dir="${work_root}/stage"
if python3 "$(dirname "${BASH_SOURCE[0]}")/validate-actions-artifact.py" --archive "${archive_path}" --output "${stage_dir}"; then
  :
else
  die "${EXIT_UNSAFE_ARCHIVE}" 'release artifact ZIP failed confinement validation'
fi

python3 - \
  "${stage_dir}/source-artifact-metadata.json" \
  "${repository}" \
  "${workflow_id}" \
  "${workflow_path}" \
  "${run_id}" \
  "${run_attempt}" \
  "${source_sha}" \
  "${artifact_id}" \
  "${artifact_name}" \
  "${artifact_digest}" <<'PY'
import json
import sys
(
    output,
    repository,
    workflow_id,
    workflow_path,
    run_id,
    run_attempt,
    source_sha,
    artifact_id,
    artifact_name,
    artifact_digest,
) = sys.argv[1:]
payload = {
    "schemaVersion": 1,
    "repository": repository,
    "workflowId": int(workflow_id),
    "workflowPath": workflow_path,
    "runId": int(run_id),
    "runAttempt": int(run_attempt),
    "sourceSHA": source_sha,
    "artifactId": int(artifact_id),
    "artifactName": artifact_name,
    "artifactDigest": artifact_digest,
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
PY

mv "${stage_dir}" "${output_dir}"
printf 'resolved release artifact run=%s attempt=%s artifact=%s\n' "${run_id}" "${run_attempt}" "${artifact_id}"
