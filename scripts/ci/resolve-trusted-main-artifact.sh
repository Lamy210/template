#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
# shellcheck source=scripts/common/repository-name.sh
source "${script_dir}/../common/repository-name.sh"

readonly EXIT_USAGE=2
readonly EXIT_INFRA=3
readonly EXIT_NOT_FOUND=4
readonly EXIT_UNSAFE_ARCHIVE=5
readonly EXIT_INTEGRITY=6

usage() {
  cat >&2 <<'EOF'
Usage: resolve-trusted-main-artifact.sh \
  --repository owner/repo \
  --workflow workflow.yml \
  --artifact exact-name \
  --output directory \
  [--branch branch-name] \
  [--max-runs 1..100] \
  [--trusted-events push[,schedule]]
EOF
}

die() {
  local status="$1"
  shift
  printf '%s\n' "$*" >&2
  exit "${status}"
}

repository=""
workflow=""
artifact_name=""
output_dir=""
branch="main"
max_runs="100"
trusted_events="push"

while (($# > 0)); do
  case "$1" in
    --repository)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --repository'
      repository="$2"
      shift 2
      ;;
    --workflow)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --workflow'
      workflow="$2"
      shift 2
      ;;
    --artifact)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --artifact'
      artifact_name="$2"
      shift 2
      ;;
    --output)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --output'
      output_dir="$2"
      shift 2
      ;;
    --branch)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --branch'
      branch="$2"
      shift 2
      ;;
    --max-runs)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --max-runs'
      max_runs="$2"
      shift 2
      ;;
    --trusted-events)
      (($# >= 2)) || die "${EXIT_USAGE}" 'missing value for --trusted-events'
      trusted_events="$2"
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

[[ -n "${repository}" ]] || die "${EXIT_USAGE}" '--repository is required'
is_canonical_repository_name "${repository}" || die "${EXIT_USAGE}" '--repository must use canonical owner/repo form'
[[ -n "${workflow}" ]] || die "${EXIT_USAGE}" '--workflow is required'
[[ "${workflow}" != */* ]] || die "${EXIT_USAGE}" '--workflow must be a workflow file name, not a path'
[[ -n "${artifact_name}" ]] || die "${EXIT_USAGE}" '--artifact is required'
[[ -n "${output_dir}" ]] || die "${EXIT_USAGE}" '--output is required'
if [[ -e "${output_dir}" || -L "${output_dir}" ]]; then
  die "${EXIT_USAGE}" '--output must not already exist'
fi
[[ -n "${branch}" ]] || die "${EXIT_USAGE}" '--branch must not be empty'
[[ "${max_runs}" =~ ^[0-9]+$ ]] || die "${EXIT_USAGE}" '--max-runs must be an integer from 1 to 100'
max_runs_number=$((10#${max_runs}))
((max_runs_number >= 1 && max_runs_number <= 100)) || die "${EXIT_USAGE}" '--max-runs must be from 1 to 100'
max_runs="${max_runs_number}"
[[ -n "${trusted_events}" ]] || die "${EXIT_USAGE}" '--trusted-events must not be empty'

IFS=',' read -r -a trusted_event_list <<<"${trusted_events}"
seen_events=","
for trusted_event in "${trusted_event_list[@]}"; do
  case "${trusted_event}" in
    push | schedule) ;;
    *) die "${EXIT_USAGE}" "untrusted workflow event in --trusted-events: ${trusted_event}" ;;
  esac
  [[ "${seen_events}" != *",${trusted_event},"* ]] || die "${EXIT_USAGE}" "duplicate trusted workflow event: ${trusted_event}"
  seen_events+="${trusted_event},"
done

[[ -n "${GH_TOKEN:-}" ]] || die "${EXIT_USAGE}" 'GH_TOKEN is required'

command -v gh >/dev/null 2>&1 || die "${EXIT_USAGE}" 'gh is required'
command -v python3 >/dev/null 2>&1 || die "${EXIT_USAGE}" 'python3 is required'

output_parent="$(dirname "${output_dir}")"
mkdir -p "${output_parent}"
work_root="$(mktemp -d "${output_parent}/.trusted-artifact.XXXXXX")"
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

api_paginated_to_file() {
  local endpoint="$1"
  local destination="$2"
  local attempt

  for attempt in 1 2 3; do
    if gh api --paginate --slurp "${endpoint}" >"${destination}"; then
      return 0
    fi
    rm -f "${destination}"
    if ((attempt < 3)); then
      sleep "${attempt}"
    fi
  done

  return 1
}

repository_identity() {
  local metadata="$1"
  python3 "${repo_root}/scripts/common/validate-repository-identity.py" \
    --metadata "${metadata}" \
    --repository "${repository}"
}

initial_repository_json="${work_root}/repository-initial.json"
api_to_file "repos/${repository}" "${initial_repository_json}" ||
  die "${EXIT_INFRA}" "failed to query trusted repository identity"

if ! initial_repository_identity="$(repository_identity "${initial_repository_json}")"; then
  die "${EXIT_INTEGRITY}" "trusted repository identity failed validation"
fi
IFS=  python3 - "${branch}" <<'PY'
import sys
import urllib.parse

print(urllib.parse.quote(sys.argv[1], safe=""))
PY
)"

raw_candidates_file="${work_root}/candidates-unsorted.tsv"
: >"${raw_candidates_file}"
for trusted_event in "${trusted_event_list[@]}"; do
  runs_json="${work_root}/runs-${trusted_event}.json"
  runs_endpoint="repos/${repository}/actions/workflows/${workflow}/runs?branch=${encoded_branch}&event=${trusted_event}&status=success&per_page=${max_runs}"
  api_to_file "${runs_endpoint}" "${runs_json}" || die "${EXIT_INFRA}" "failed to query ${trusted_event} workflow runs"

  if python3 - "${runs_json}" "${trusted_repository_name}" "${trusted_repository_id}" "${branch}" "${trusted_event}" >>"${raw_candidates_file}" <<'PY'
import json
import re
import sys

path, expected_repo, expected_repo_id_text, expected_branch, expected_event = sys.argv[1:6]
expected_repo_id = int(expected_repo_id_text)
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    runs = payload["workflow_runs"]
    if not isinstance(runs, list):
        raise TypeError("workflow_runs must be a list")
except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"invalid workflow-runs response: {error}", file=sys.stderr)
    raise SystemExit(1)

for run in runs:
    if not isinstance(run, dict):
        continue
    head_repository = run.get("head_repository")
    run_repository = run.get("repository")
    if not isinstance(head_repository, dict) or not isinstance(run_repository, dict):
        continue
    if head_repository.get("id") != expected_repo_id:
        continue
    if run_repository.get("id") != expected_repo_id:
        continue
    head_full_name = head_repository.get("full_name")
    run_full_name = run_repository.get("full_name")
    if not isinstance(head_full_name, str) or head_full_name.casefold() != expected_repo.casefold():
        continue
    if not isinstance(run_full_name, str) or run_full_name.casefold() != expected_repo.casefold():
        continue
    if run.get("head_branch") != expected_branch:
        continue
    if run.get("event") != expected_event:
        continue
    if run.get("conclusion") != "success":
        continue

    run_id = run.get("id")
    attempt = run.get("run_attempt")
    head_sha = run.get("head_sha")
    if (
        type(run_id) is not int
        or run_id <= 0
        or type(attempt) is not int
        or attempt <= 0
        or not isinstance(head_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
    ):
        continue

    print(f"{run_id}\t{attempt}\t{head_sha}\t{expected_event}")
PY
  then
    :
  else
    die "${EXIT_INFRA}" "${trusted_event} workflow-runs response was malformed"
  fi
done

candidates_file="${work_root}/candidates.tsv"
python3 - "${raw_candidates_file}" "${candidates_file}" <<'PY'
import sys

source, destination = sys.argv[1:3]
rows = []
with open(source, encoding="utf-8") as handle:
    for line in handle:
        line = line.rstrip("\n")
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            raise SystemExit("malformed trusted workflow candidate")
        rows.append((int(fields[0]), line))
rows.sort(key=lambda item: item[0], reverse=True)
with open(destination, "w", encoding="utf-8") as handle:
    for _run_id, line in rows:
        handle.write(line + "\n")
PY

selected_run_id=""
selected_run_attempt=""
selected_source_sha=""
selected_event=""
selected_artifact_id=""
selected_artifact_digest=""

while IFS=$'\t' read -r run_id run_attempt source_sha run_event; do
  [[ -n "${run_id}" ]] || continue

  artifacts_json="${work_root}/artifacts-${run_id}.json"
  artifacts_endpoint="repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100"
  api_paginated_to_file "${artifacts_endpoint}" "${artifacts_json}" || die "${EXIT_INFRA}" "failed to query artifacts for run ${run_id}"

  artifact_result="${work_root}/artifact-${run_id}.tsv"
  if python3 - "${artifacts_json}" "${artifact_name}" "${trusted_repository_id}" "${run_id}" "${source_sha}" >"${artifact_result}" <<'PY'
import json
import sys

path, expected_name, repository_id_text, run_id_text, expected_sha = sys.argv[1:6]
expected_repository_id = int(repository_id_text)
expected_run_id = int(run_id_text)
try:
    with open(path, encoding="utf-8") as handle:
        pages = json.load(handle)
    if not isinstance(pages, list) or not pages:
        raise TypeError("paginated artifacts response must be a non-empty list")
except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"invalid artifacts response: {error}", file=sys.stderr)
    raise SystemExit(1)

artifacts = []
declared_total = None
seen_ids = set()

for page in pages:
    if not isinstance(page, dict):
        print("artifact page must be an object", file=sys.stderr)
        raise SystemExit(1)
    page_artifacts = page.get("artifacts")
    total_count = page.get("total_count")
    if not isinstance(page_artifacts, list):
        print("artifact page is missing artifacts list", file=sys.stderr)
        raise SystemExit(1)
    if type(total_count) is not int or total_count < 0:
        print("artifact page total_count is invalid", file=sys.stderr)
        raise SystemExit(1)
    if declared_total is None:
        declared_total = total_count
    elif total_count != declared_total:
        print("artifact pages disagree on total_count", file=sys.stderr)
        raise SystemExit(1)

    for artifact in page_artifacts:
        if not isinstance(artifact, dict):
            print("artifact entry must be an object", file=sys.stderr)
            raise SystemExit(1)
        artifact_id = artifact.get("id")
        if type(artifact_id) is not int or artifact_id <= 0:
            print("artifact id is missing or invalid", file=sys.stderr)
            raise SystemExit(1)
        if artifact_id in seen_ids:
            print(f"duplicate artifact id across pages: {artifact_id}", file=sys.stderr)
            raise SystemExit(1)
        seen_ids.add(artifact_id)
        artifacts.append(artifact)

if declared_total != len(artifacts):
    print(
        f"artifact total_count={declared_total} does not match fetched entries={len(artifacts)}",
        file=sys.stderr,
    )
    raise SystemExit(1)

matches = [
    artifact
    for artifact in artifacts
    if artifact.get("name") == expected_name
    and artifact.get("expired") is False
]

if len(matches) > 1:
    print("multiple non-expired artifacts have the exact requested name", file=sys.stderr)
    raise SystemExit(2)
if not matches:
    raise SystemExit(0)

artifact = matches[0]
artifact_id = artifact.get("id")
if type(artifact_id) is not int or artifact_id <= 0:
    print("artifact id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)

workflow_run = artifact.get("workflow_run")
if not isinstance(workflow_run, dict):
    print("trusted artifact is missing workflow_run identity", file=sys.stderr)
    raise SystemExit(3)
if workflow_run.get("id") != expected_run_id:
    print("trusted artifact workflow_run.id does not match selected run", file=sys.stderr)
    raise SystemExit(3)
if workflow_run.get("repository_id") != expected_repository_id:
    print("trusted artifact repository_id does not match trusted repository", file=sys.stderr)
    raise SystemExit(3)
if workflow_run.get("head_repository_id") != expected_repository_id:
    print("trusted artifact head_repository_id does not match trusted repository", file=sys.stderr)
    raise SystemExit(3)
if workflow_run.get("head_sha") != expected_sha:
    print("trusted artifact workflow_run.head_sha does not match selected run", file=sys.stderr)
    raise SystemExit(3)

digest = artifact.get("digest")
if digest is not None and not isinstance(digest, str):
    print("artifact digest is invalid", file=sys.stderr)
    raise SystemExit(1)
print(f"{artifact_id}\t{digest or ''}")
PY
  then
    :
  else
    parser_status=$?
    if ((parser_status == 2)); then
      die "${EXIT_INFRA}" "ambiguous exact-name artifacts for run ${run_id}"
    fi
    if ((parser_status == 3)); then
      die "${EXIT_INTEGRITY}" "trusted artifact workflow_run identity mismatch for run ${run_id}"
    fi
    die "${EXIT_INFRA}" "artifacts response for run ${run_id} was malformed"
  fi

  if [[ ! -s "${artifact_result}" ]]; then
    continue
  fi

  IFS=$'\t' read -r selected_artifact_id selected_artifact_digest <"${artifact_result}"
  selected_run_id="${run_id}"
  selected_run_attempt="${run_attempt}"
  selected_source_sha="${source_sha}"
  selected_event="${run_event}"
  break
done <"${candidates_file}"

[[ -n "${selected_run_id}" ]] || die "${EXIT_NOT_FOUND}" "no trusted artifact candidate found on branch ${branch}"

if [[ ! "${selected_artifact_digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  die "${EXIT_INTEGRITY}" 'trusted artifact is missing a valid SHA-256 digest'
fi

archive_path="${work_root}/artifact.zip"
archive_endpoint="repos/${repository}/actions/artifacts/${selected_artifact_id}/zip"
api_to_file "${archive_endpoint}" "${archive_path}" || die "${EXIT_INFRA}" 'failed to download artifact archive'

actual_archive_digest="$(
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
if [[ "${actual_archive_digest}" != "${selected_artifact_digest}" ]]; then
  die "${EXIT_INTEGRITY}" "artifact digest mismatch: expected ${selected_artifact_digest}, got ${actual_archive_digest}"
fi

stage_dir="${work_root}/stage"
mkdir -p "${stage_dir}"
if python3 - "${archive_path}" "${stage_dir}" <<'PY'
import os
import pathlib
import shutil
import stat
import sys
import zipfile

archive_path, destination = sys.argv[1:3]
destination_path = pathlib.Path(destination).resolve()
seen: set[str] = set()

try:
    archive = zipfile.ZipFile(archive_path)
except (OSError, zipfile.BadZipFile) as error:
    print(f"invalid ZIP archive: {error}", file=sys.stderr)
    raise SystemExit(1)

with archive:
    members = archive.infolist()
    for member in members:
        raw = member.filename
        if not raw or "\\" in raw or raw.startswith("/"):
            print(f"unsafe archive member: {raw!r}", file=sys.stderr)
            raise SystemExit(2)
        if len(raw) >= 2 and raw[0].isalpha() and raw[1] == ":":
            print(f"unsafe drive-prefixed archive member: {raw!r}", file=sys.stderr)
            raise SystemExit(2)

        pure = pathlib.PurePosixPath(raw)
        if any(part == ".." for part in pure.parts):
            print(f"archive traversal is not allowed: {raw!r}", file=sys.stderr)
            raise SystemExit(2)

        canonical_parts = [part for part in pure.parts if part not in ("", ".")]
        if not canonical_parts:
            continue
        canonical = "/".join(canonical_parts)
        if canonical in seen:
            print(f"duplicate canonical archive member: {canonical!r}", file=sys.stderr)
            raise SystemExit(2)
        seen.add(canonical)

        mode = (member.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            target = archive.read(member).decode("utf-8", errors="strict")
            link_parent = pathlib.PurePosixPath(canonical).parent
            resolved_link = pathlib.PurePosixPath(link_parent, target)
            parts: list[str] = []
            for part in resolved_link.parts:
                if part in ("", "."):
                    continue
                if part == "..":
                    if not parts:
                        print(f"symlink escapes extraction root: {canonical!r}", file=sys.stderr)
                        raise SystemExit(2)
                    parts.pop()
                else:
                    parts.append(part)
            # Symlinks are data we do not need for baseline bundles. Even an
            # internal link is rejected to keep extraction semantics uniform.
            print(f"symlink archive members are not allowed: {canonical!r}", file=sys.stderr)
            raise SystemExit(2)

    for member in members:
        raw = member.filename
        if not raw:
            continue
        pure = pathlib.PurePosixPath(raw)
        canonical_parts = [part for part in pure.parts if part not in ("", ".")]
        if not canonical_parts:
            continue
        target = destination_path.joinpath(*canonical_parts)
        resolved_parent = target.parent.resolve()
        if os.path.commonpath([str(destination_path), str(resolved_parent)]) != str(destination_path):
            print(f"archive member escapes extraction root: {raw!r}", file=sys.stderr)
            raise SystemExit(2)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, open(target, "wb") as sink:
            shutil.copyfileobj(source, sink)
PY
then
  :
else
  archive_status=$?
  if ((archive_status == 2)); then
    die "${EXIT_UNSAFE_ARCHIVE}" 'artifact archive failed safety validation'
  fi
  die "${EXIT_INFRA}" 'artifact archive could not be decoded'
fi

final_repository_json="${work_root}/repository-final.json"
api_to_file "repos/${repository}" "${final_repository_json}" ||
  die "${EXIT_INFRA}" "failed to re-query trusted repository identity"

if ! final_repository_identity="$(repository_identity "${final_repository_json}")"; then
  die "${EXIT_INTEGRITY}" "final trusted repository identity failed validation"
fi
if [[ "${final_repository_identity}" != "${initial_repository_identity}" ]]; then
  die "${EXIT_INTEGRITY}" "trusted repository identity changed during artifact resolution"
fi

python3 - \
  "${stage_dir}/resolver-metadata.json" \
  "${trusted_repository_name}" \
  "${trusted_repository_id}" \
  "${workflow}" \
  "${branch}" \
  "${selected_run_id}" \
  "${selected_run_attempt}" \
  "${selected_source_sha}" \
  "${selected_event}" \
  "${selected_artifact_id}" \
  "${artifact_name}" \
  "${selected_artifact_digest}" <<'PY'
import datetime
import json
import sys

(
    output,
    repository,
    repository_id,
    workflow,
    branch,
    run_id,
    run_attempt,
    source_sha,
    event,
    artifact_id,
    artifact_name,
    artifact_digest,
) = sys.argv[1:]

payload = {
    "schemaVersion": 1,
    "repository": repository,
    "repositoryId": int(repository_id),
    "workflow": workflow,
    "branch": branch,
    "runId": int(run_id),
    "runAttempt": int(run_attempt),
    "sourceSHA": source_sha,
    "event": event,
    "artifactId": int(artifact_id),
    "artifactName": artifact_name,
    "artifactDigest": artifact_digest,
    "retrievedAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
PY

mv "${stage_dir}" "${output_dir}"
printf '%s\n' "${selected_run_id}"
\t' read -r trusted_repository_id trusted_repository_name <<<"${initial_repository_identity}"
if [[ ! "${trusted_repository_id}" =~ ^[1-9][0-9]*$ ]] ||
  ! is_canonical_repository_name "${trusted_repository_name}"; then
  die "${EXIT_INTEGRITY}" "trusted repository identity output was malformed"
fi

encoded_branch="$(
  python3 - "${branch}" <<'PY'
import sys
import urllib.parse

print(urllib.parse.quote(sys.argv[1], safe=""))
PY
)"

raw_candidates_file="${work_root}/candidates-unsorted.tsv"
: >"${raw_candidates_file}"
for trusted_event in "${trusted_event_list[@]}"; do
  runs_json="${work_root}/runs-${trusted_event}.json"
  runs_endpoint="repos/${repository}/actions/workflows/${workflow}/runs?branch=${encoded_branch}&event=${trusted_event}&status=success&per_page=${max_runs}"
  api_to_file "${runs_endpoint}" "${runs_json}" || die "${EXIT_INFRA}" "failed to query ${trusted_event} workflow runs"

  if python3 - "${runs_json}" "${repository}" "${branch}" "${trusted_event}" >>"${raw_candidates_file}" <<'PY'
import json
import sys

path, expected_repo, expected_branch, expected_event = sys.argv[1:5]
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    runs = payload["workflow_runs"]
    if not isinstance(runs, list):
        raise TypeError("workflow_runs must be a list")
except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"invalid workflow-runs response: {error}", file=sys.stderr)
    raise SystemExit(1)

for run in runs:
    if not isinstance(run, dict):
        continue
    head_repository = run.get("head_repository")
    if not isinstance(head_repository, dict):
        continue
    if head_repository.get("full_name") != expected_repo:
        continue
    if run.get("head_branch") != expected_branch:
        continue
    if run.get("event") != expected_event:
        continue
    if run.get("conclusion") != "success":
        continue

    run_id = run.get("id")
    attempt = run.get("run_attempt")
    head_sha = run.get("head_sha")
    if not isinstance(run_id, int) or not isinstance(attempt, int) or not isinstance(head_sha, str) or not head_sha:
        continue

    print(f"{run_id}\t{attempt}\t{head_sha}\t{expected_event}")
PY
  then
    :
  else
    die "${EXIT_INFRA}" "${trusted_event} workflow-runs response was malformed"
  fi
done

candidates_file="${work_root}/candidates.tsv"
python3 - "${raw_candidates_file}" "${candidates_file}" <<'PY'
import sys

source, destination = sys.argv[1:3]
rows = []
with open(source, encoding="utf-8") as handle:
    for line in handle:
        line = line.rstrip("\n")
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            raise SystemExit("malformed trusted workflow candidate")
        rows.append((int(fields[0]), line))
rows.sort(key=lambda item: item[0], reverse=True)
with open(destination, "w", encoding="utf-8") as handle:
    for _run_id, line in rows:
        handle.write(line + "\n")
PY

selected_run_id=""
selected_run_attempt=""
selected_source_sha=""
selected_event=""
selected_artifact_id=""
selected_artifact_digest=""

while IFS=$'\t' read -r run_id run_attempt source_sha run_event; do
  [[ -n "${run_id}" ]] || continue

  artifacts_json="${work_root}/artifacts-${run_id}.json"
  artifacts_endpoint="repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100"
  api_paginated_to_file "${artifacts_endpoint}" "${artifacts_json}" || die "${EXIT_INFRA}" "failed to query artifacts for run ${run_id}"

  artifact_result="${work_root}/artifact-${run_id}.tsv"
  if python3 - "${artifacts_json}" "${artifact_name}" >"${artifact_result}" <<'PY'
import json
import sys

path, expected_name = sys.argv[1:3]
try:
    with open(path, encoding="utf-8") as handle:
        pages = json.load(handle)
    if not isinstance(pages, list) or not pages:
        raise TypeError("paginated artifacts response must be a non-empty list")
except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"invalid artifacts response: {error}", file=sys.stderr)
    raise SystemExit(1)

artifacts = []
declared_total = None
seen_ids = set()

for page in pages:
    if not isinstance(page, dict):
        print("artifact page must be an object", file=sys.stderr)
        raise SystemExit(1)
    page_artifacts = page.get("artifacts")
    total_count = page.get("total_count")
    if not isinstance(page_artifacts, list):
        print("artifact page is missing artifacts list", file=sys.stderr)
        raise SystemExit(1)
    if type(total_count) is not int or total_count < 0:
        print("artifact page total_count is invalid", file=sys.stderr)
        raise SystemExit(1)
    if declared_total is None:
        declared_total = total_count
    elif total_count != declared_total:
        print("artifact pages disagree on total_count", file=sys.stderr)
        raise SystemExit(1)

    for artifact in page_artifacts:
        if not isinstance(artifact, dict):
            print("artifact entry must be an object", file=sys.stderr)
            raise SystemExit(1)
        artifact_id = artifact.get("id")
        if type(artifact_id) is not int or artifact_id <= 0:
            print("artifact id is missing or invalid", file=sys.stderr)
            raise SystemExit(1)
        if artifact_id in seen_ids:
            print(f"duplicate artifact id across pages: {artifact_id}", file=sys.stderr)
            raise SystemExit(1)
        seen_ids.add(artifact_id)
        artifacts.append(artifact)

if declared_total != len(artifacts):
    print(
        f"artifact total_count={declared_total} does not match fetched entries={len(artifacts)}",
        file=sys.stderr,
    )
    raise SystemExit(1)

matches = [
    artifact
    for artifact in artifacts
    if artifact.get("name") == expected_name
    and artifact.get("expired") is False
]

if len(matches) > 1:
    print("multiple non-expired artifacts have the exact requested name", file=sys.stderr)
    raise SystemExit(2)
if not matches:
    raise SystemExit(0)

artifact = matches[0]
artifact_id = artifact.get("id")
if not isinstance(artifact_id, int):
    print("artifact id is missing or invalid", file=sys.stderr)
    raise SystemExit(1)
digest = artifact.get("digest")
if digest is not None and not isinstance(digest, str):
    print("artifact digest is invalid", file=sys.stderr)
    raise SystemExit(1)
print(f"{artifact_id}\t{digest or ''}")
PY
  then
    :
  else
    parser_status=$?
    if ((parser_status == 2)); then
      die "${EXIT_INFRA}" "ambiguous exact-name artifacts for run ${run_id}"
    fi
    die "${EXIT_INFRA}" "artifacts response for run ${run_id} was malformed"
  fi

  if [[ ! -s "${artifact_result}" ]]; then
    continue
  fi

  IFS=$'\t' read -r selected_artifact_id selected_artifact_digest <"${artifact_result}"
  selected_run_id="${run_id}"
  selected_run_attempt="${run_attempt}"
  selected_source_sha="${source_sha}"
  selected_event="${run_event}"
  break
done <"${candidates_file}"

[[ -n "${selected_run_id}" ]] || die "${EXIT_NOT_FOUND}" "no trusted artifact candidate found on branch ${branch}"

if [[ ! "${selected_artifact_digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  die "${EXIT_INTEGRITY}" 'trusted artifact is missing a valid SHA-256 digest'
fi

archive_path="${work_root}/artifact.zip"
archive_endpoint="repos/${repository}/actions/artifacts/${selected_artifact_id}/zip"
api_to_file "${archive_endpoint}" "${archive_path}" || die "${EXIT_INFRA}" 'failed to download artifact archive'

actual_archive_digest="$(
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
if [[ "${actual_archive_digest}" != "${selected_artifact_digest}" ]]; then
  die "${EXIT_INTEGRITY}" "artifact digest mismatch: expected ${selected_artifact_digest}, got ${actual_archive_digest}"
fi

stage_dir="${work_root}/stage"
mkdir -p "${stage_dir}"
if python3 - "${archive_path}" "${stage_dir}" <<'PY'
import os
import pathlib
import shutil
import stat
import sys
import zipfile

archive_path, destination = sys.argv[1:3]
destination_path = pathlib.Path(destination).resolve()
seen: set[str] = set()

try:
    archive = zipfile.ZipFile(archive_path)
except (OSError, zipfile.BadZipFile) as error:
    print(f"invalid ZIP archive: {error}", file=sys.stderr)
    raise SystemExit(1)

with archive:
    members = archive.infolist()
    for member in members:
        raw = member.filename
        if not raw or "\\" in raw or raw.startswith("/"):
            print(f"unsafe archive member: {raw!r}", file=sys.stderr)
            raise SystemExit(2)
        if len(raw) >= 2 and raw[0].isalpha() and raw[1] == ":":
            print(f"unsafe drive-prefixed archive member: {raw!r}", file=sys.stderr)
            raise SystemExit(2)

        pure = pathlib.PurePosixPath(raw)
        if any(part == ".." for part in pure.parts):
            print(f"archive traversal is not allowed: {raw!r}", file=sys.stderr)
            raise SystemExit(2)

        canonical_parts = [part for part in pure.parts if part not in ("", ".")]
        if not canonical_parts:
            continue
        canonical = "/".join(canonical_parts)
        if canonical in seen:
            print(f"duplicate canonical archive member: {canonical!r}", file=sys.stderr)
            raise SystemExit(2)
        seen.add(canonical)

        mode = (member.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            target = archive.read(member).decode("utf-8", errors="strict")
            link_parent = pathlib.PurePosixPath(canonical).parent
            resolved_link = pathlib.PurePosixPath(link_parent, target)
            parts: list[str] = []
            for part in resolved_link.parts:
                if part in ("", "."):
                    continue
                if part == "..":
                    if not parts:
                        print(f"symlink escapes extraction root: {canonical!r}", file=sys.stderr)
                        raise SystemExit(2)
                    parts.pop()
                else:
                    parts.append(part)
            # Symlinks are data we do not need for baseline bundles. Even an
            # internal link is rejected to keep extraction semantics uniform.
            print(f"symlink archive members are not allowed: {canonical!r}", file=sys.stderr)
            raise SystemExit(2)

    for member in members:
        raw = member.filename
        if not raw:
            continue
        pure = pathlib.PurePosixPath(raw)
        canonical_parts = [part for part in pure.parts if part not in ("", ".")]
        if not canonical_parts:
            continue
        target = destination_path.joinpath(*canonical_parts)
        resolved_parent = target.parent.resolve()
        if os.path.commonpath([str(destination_path), str(resolved_parent)]) != str(destination_path):
            print(f"archive member escapes extraction root: {raw!r}", file=sys.stderr)
            raise SystemExit(2)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, open(target, "wb") as sink:
            shutil.copyfileobj(source, sink)
PY
then
  :
else
  archive_status=$?
  if ((archive_status == 2)); then
    die "${EXIT_UNSAFE_ARCHIVE}" 'artifact archive failed safety validation'
  fi
  die "${EXIT_INFRA}" 'artifact archive could not be decoded'
fi

python3 - \
  "${stage_dir}/resolver-metadata.json" \
  "${repository}" \
  "${workflow}" \
  "${branch}" \
  "${selected_run_id}" \
  "${selected_run_attempt}" \
  "${selected_source_sha}" \
  "${selected_event}" \
  "${selected_artifact_id}" \
  "${artifact_name}" \
  "${selected_artifact_digest}" <<'PY'
import datetime
import json
import sys

(
    output,
    repository,
    workflow,
    branch,
    run_id,
    run_attempt,
    source_sha,
    event,
    artifact_id,
    artifact_name,
    artifact_digest,
) = sys.argv[1:]

payload = {
    "schemaVersion": 1,
    "repository": repository,
    "workflow": workflow,
    "branch": branch,
    "runId": int(run_id),
    "runAttempt": int(run_attempt),
    "sourceSHA": source_sha,
    "event": event,
    "artifactId": int(artifact_id),
    "artifactName": artifact_name,
    "artifactDigest": artifact_digest,
    "retrievedAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
PY

mv "${stage_dir}" "${output_dir}"
printf '%s\n' "${selected_run_id}"
