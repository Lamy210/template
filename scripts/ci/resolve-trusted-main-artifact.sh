#!/usr/bin/env bash
set -euo pipefail

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
workflow=""
artifact_name=""
output_dir=""

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
[[ "${repository}" == */* ]] || die "${EXIT_USAGE}" '--repository must be owner/repo'
[[ -n "${workflow}" ]] || die "${EXIT_USAGE}" '--workflow is required'
[[ "${workflow}" != */* ]] || die "${EXIT_USAGE}" '--workflow must be a workflow file name, not a path'
[[ -n "${artifact_name}" ]] || die "${EXIT_USAGE}" '--artifact is required'
[[ -n "${output_dir}" ]] || die "${EXIT_USAGE}" '--output is required'
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

runs_json="${work_root}/runs.json"
runs_endpoint="repos/${repository}/actions/workflows/${workflow}/runs?branch=main&event=push&status=success&per_page=20"
api_to_file "${runs_endpoint}" "${runs_json}" || die "${EXIT_INFRA}" 'failed to query workflow runs'

candidates_file="${work_root}/candidates.tsv"
if python3 - "${runs_json}" "${repository}" >"${candidates_file}" <<'PY'
import json
import sys

path, expected_repo = sys.argv[1:3]
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
    if run.get("head_branch") != "main":
        continue
    if run.get("event") != "push":
        continue
    if run.get("conclusion") != "success":
        continue

    run_id = run.get("id")
    attempt = run.get("run_attempt")
    head_sha = run.get("head_sha")
    if not isinstance(run_id, int) or not isinstance(attempt, int) or not isinstance(head_sha, str) or not head_sha:
        continue

    print(f"{run_id}\t{attempt}\t{head_sha}")
PY
then
  :
else
  die "${EXIT_INFRA}" 'workflow-runs response was malformed'
fi

selected_run_id=""
selected_run_attempt=""
selected_source_sha=""
selected_artifact_id=""
selected_artifact_digest=""

while IFS=$'\t' read -r run_id run_attempt source_sha; do
  [[ -n "${run_id}" ]] || continue

  artifacts_json="${work_root}/artifacts-${run_id}.json"
  artifacts_endpoint="repos/${repository}/actions/runs/${run_id}/artifacts?per_page=100"
  api_to_file "${artifacts_endpoint}" "${artifacts_json}" || die "${EXIT_INFRA}" "failed to query artifacts for run ${run_id}"

  artifact_result="${work_root}/artifact-${run_id}.tsv"
  if python3 - "${artifacts_json}" "${artifact_name}" >"${artifact_result}" <<'PY'
import json
import sys

path, expected_name = sys.argv[1:3]
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list):
        raise TypeError("artifacts must be a list")
except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
    print(f"invalid artifacts response: {error}", file=sys.stderr)
    raise SystemExit(1)

matches = [
    artifact
    for artifact in artifacts
    if isinstance(artifact, dict)
    and artifact.get("name") == expected_name
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
  break
done <"${candidates_file}"

[[ -n "${selected_run_id}" ]] || die "${EXIT_NOT_FOUND}" 'no trusted main artifact candidate found'

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
  "${selected_run_id}" \
  "${selected_run_attempt}" \
  "${selected_source_sha}" \
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
    "workflow": workflow,
    "runId": int(run_id),
    "runAttempt": int(run_attempt),
    "sourceSHA": source_sha,
    "artifactId": int(artifact_id),
    "artifactName": artifact_name,
    "artifactDigest": artifact_digest,
    "retrievedAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
PY

rm -rf "${output_dir}"
mv "${stage_dir}" "${output_dir}"
printf '%s\n' "${selected_run_id}"
