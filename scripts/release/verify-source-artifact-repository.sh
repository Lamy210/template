#!/usr/bin/env bash
set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_INFRA=3
readonly EXIT_REJECTED=4

usage() {
  cat >&2 <<'EOF'
Usage: verify-source-artifact-repository.sh \
  --repository owner/repo \
  --repository-id 123 \
  --source-metadata path/to/source-artifact-metadata.json
EOF
}

die() {
  local status="$1"
  shift
  printf '%s\n' "$*" >&2
  exit "${status}"
}

repository=""
repository_id=""
source_metadata=""

while (($# > 0)); do
  case "$1" in
    --repository)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --repository'
      repository="$2"
      shift 2
      ;;
    --repository-id)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --repository-id'
      repository_id="$2"
      shift 2
      ;;
    --source-metadata)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --source-metadata'
      source_metadata="$2"
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
[[ "${repository_id}" =~ ^[0-9]+$ ]] || die "${EXIT_USAGE}" '--repository-id must be a positive integer'
repository_id_number=$((10#${repository_id}))
((repository_id_number > 0)) || die "${EXIT_USAGE}" '--repository-id must be positive'
repository_id="${repository_id_number}"
[[ -f "${source_metadata}" ]] || die "${EXIT_USAGE}" '--source-metadata must be an existing file'
[[ -n "${GH_TOKEN:-}" ]] || die "${EXIT_USAGE}" 'GH_TOKEN is required'
command -v gh >/dev/null 2>&1 || die "${EXIT_USAGE}" 'gh is required'
command -v python3 >/dev/null 2>&1 || die "${EXIT_USAGE}" 'python3 is required'

if identity="$(
  python3 - "${source_metadata}" <<'PY'
import json
import re
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        metadata = json.load(handle)
except (OSError, json.JSONDecodeError) as error:
    print(f"source metadata is unreadable: {error}", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(metadata, dict):
    print("source metadata must be a JSON object", file=sys.stderr)
    raise SystemExit(1)

artifact_id = metadata.get("artifactId")
run_id = metadata.get("runId")
source_sha = metadata.get("sourceSHA")
if type(artifact_id) is not int or artifact_id <= 0:
    print("source metadata artifactId must be a positive integer", file=sys.stderr)
    raise SystemExit(1)
if type(run_id) is not int or run_id <= 0:
    print("source metadata runId must be a positive integer", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(source_sha, str) or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
    print("source metadata sourceSHA must be 40 lowercase hexadecimal characters", file=sys.stderr)
    raise SystemExit(1)
print(f"{artifact_id}\t{run_id}\t{source_sha}")
PY
)"; then
  :
else
  die "${EXIT_INFRA}" 'source artifact metadata is malformed'
fi
IFS=$'\t' read -r artifact_id run_id source_sha <<<"${identity}"

work_root="$(mktemp -d)"
trap 'rm -rf "${work_root}"' EXIT
artifact_json="${work_root}/artifact.json"
if ! gh api "repos/${repository}/actions/artifacts/${artifact_id}" >"${artifact_json}"; then
  die "${EXIT_INFRA}" 'failed to query exact source Artifact metadata'
fi

if python3 - "${artifact_json}" "${artifact_id}" "${run_id}" "${source_sha}" "${repository_id}" <<'PY'
import json
import re
import sys

path, artifact_id_text, run_id_text, expected_sha, repository_id_text = sys.argv[1:]
expected_artifact_id = int(artifact_id_text)
expected_run_id = int(run_id_text)
expected_repository_id = int(repository_id_text)

try:
    with open(path, encoding="utf-8") as handle:
        artifact = json.load(handle)
except (OSError, json.JSONDecodeError) as error:
    print(f"Artifact API response is unreadable: {error}", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(artifact, dict):
    print("Artifact API response must be a JSON object", file=sys.stderr)
    raise SystemExit(1)
artifact_id = artifact.get("id")
workflow_run = artifact.get("workflow_run")
if type(artifact_id) is not int or artifact_id <= 0:
    print("Artifact API id must be a positive integer", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(workflow_run, dict):
    print("Artifact API workflow_run metadata is missing or invalid", file=sys.stderr)
    raise SystemExit(1)

run_id = workflow_run.get("id")
repository_id = workflow_run.get("repository_id")
head_repository_id = workflow_run.get("head_repository_id")
head_sha = workflow_run.get("head_sha")
for field, value in (
    ("workflow_run.id", run_id),
    ("workflow_run.repository_id", repository_id),
    ("workflow_run.head_repository_id", head_repository_id),
):
    if type(value) is not int or value <= 0:
        print(f"Artifact API {field} must be a positive integer", file=sys.stderr)
        raise SystemExit(1)
if not isinstance(head_sha, str) or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None:
    print("Artifact API workflow_run.head_sha is invalid", file=sys.stderr)
    raise SystemExit(1)

checks = (
    (artifact_id == expected_artifact_id, "source Artifact ID mismatch"),
    (run_id == expected_run_id, "source Artifact workflow run ID mismatch"),
    (head_sha == expected_sha, "source Artifact workflow run SHA mismatch"),
    (repository_id == expected_repository_id, "source Artifact repository ID mismatch"),
    (head_repository_id == expected_repository_id, "source Artifact head repository ID mismatch"),
)
for condition, message in checks:
    if not condition:
        print(message, file=sys.stderr)
        raise SystemExit(2)
PY
then
  printf 'verified source Artifact repository identity artifact=%s run=%s\n' "${artifact_id}" "${run_id}"
else
  status=$?
  if ((status == 2)); then
    die "${EXIT_REJECTED}" 'source Artifact failed repository identity validation'
  fi
  die "${EXIT_INFRA}" 'source Artifact API metadata is malformed'
fi
