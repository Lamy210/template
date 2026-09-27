#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  audit-post-split-runtime-proof.sh \
    owner/repo SOURCE_RUN_ID PUBLISHER_RUN_ID \
    [--evidence-output post-split-proof.json]

Read-only audit for a disposable-repository two-stage release proof.
Run it immediately after the proof while the publisher workflow SHA is still
the repository default-branch head. When --evidence-output is supplied, the
validated proof facts are written only after the audit succeeds.
EOF
}

repository="${1:-}"
source_run_id="${2:-}"
publisher_run_id="${3:-}"
if [[ ! "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] ||
  [[ ! "${source_run_id}" =~ ^[1-9][0-9]*$ ]] ||
  [[ ! "${publisher_run_id}" =~ ^[1-9][0-9]*$ ]]; then
  usage
  exit 2
fi

shift 3
evidence_output=""
if (($#)); then
  if (($# != 2)) || [[ "${1:-}" != "--evidence-output" ]] || [[ -z "${2:-}" ]]; then
    usage
    exit 2
  fi
  evidence_output="${2}"
fi

if [[ -n "${evidence_output}" ]]; then
  if [[ -e "${evidence_output}" || -L "${evidence_output}" ]]; then
    echo "--evidence-output must not already exist: ${evidence_output}" >&2
    exit 2
  fi
  evidence_parent="$(dirname -- "${evidence_output}")"
  if [[ ! -d "${evidence_parent}" || ! -w "${evidence_parent}" ]]; then
    echo "--evidence-output parent must be an existing writable directory: ${evidence_parent}" >&2
    exit 2
  fi
fi

for command_name in gh python3; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/post-split-runtime-proof.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

gh api "${api_headers[@]}" "repos/${repository}" >"${temp_root}/repository.json"

default_branch="$(
  python3 - "${temp_root}/repository.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
branch = document.get("default_branch")
if not isinstance(branch, str) or not branch:
    raise SystemExit("repository response has no default_branch")
print(branch)
PY
)"

encoded_default_branch="$(
  python3 - "${default_branch}" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
)"

gh api "${api_headers[@]}" "repos/${repository}/commits/${encoded_default_branch}" >"${temp_root}/default-commit.json"

gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${source_run_id}" >"${temp_root}/source-run.json"

source_sha="$(
  python3 - "${temp_root}/source-run.json" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
sha = document.get("head_sha")
if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("source run head_sha is invalid")
print(sha)
PY
)"

gh api "${api_headers[@]}" "repos/${repository}/contents/.github/workflows/release-build.yml?ref=${source_sha}" >"${temp_root}/source-workflow.json"

source_tag="$(
  python3 - "${temp_root}/source-run.json" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
tag = document.get("head_branch")
if not isinstance(tag, str) or re.fullmatch(
    r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)",
    tag,
) is None:
    raise SystemExit("source run head_branch is not canonical stable SemVer")
print(tag)
PY
)"

gh api "${api_headers[@]}" "repos/${repository}/git/ref/tags/${source_tag}" >"${temp_root}/tag-ref.json"

tag_objects_dir="${temp_root}/tag-objects"
mkdir -p "${tag_objects_dir}"
current_tag_object_file="${temp_root}/tag-ref.json"
resolved_tag_sha=""
for depth in 1 2 3 4 5 6 7 8; do
  readarray -t current_tag_object < <(
    python3 - "${current_tag_object_file}" <<'PY'
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
if not isinstance(document, dict):
    raise SystemExit("GitHub tag/ref response must be an object")
target = document.get("object")
if not isinstance(target, dict):
    raise SystemExit("GitHub tag/ref response is missing object metadata")
object_type = target.get("type")
object_sha = target.get("sha")
if object_type not in {"commit", "tag"}:
    raise SystemExit(f"unsupported GitHub tag target type: {object_type!r}")
if not isinstance(object_sha, str) or re.fullmatch(r"[0-9a-f]{40}", object_sha) is None:
    raise SystemExit("GitHub tag target SHA is invalid")
print(object_type)
print(object_sha)
PY
  )
  if (("${#current_tag_object[@]}" != 2)); then
    echo "GitHub tag target identity output was malformed." >&2
    exit 3
  fi
  object_type="${current_tag_object[0]}"
  object_sha="${current_tag_object[1]}"

  if [[ "${object_type}" == "commit" ]]; then
    resolved_tag_sha="${object_sha}"
    break
  fi

  current_tag_object_file="${tag_objects_dir}/tag-object-${depth}.json"
  gh api "${api_headers[@]}" "repos/${repository}/git/tags/${object_sha}" >"${current_tag_object_file}"
done

if [[ -z "${resolved_tag_sha}" ]]; then
  echo "Live release tag exceeded maximum annotated-tag dereference depth." >&2
  exit 3
fi

python3 - "${tag_objects_dir}" "${temp_root}/tag-objects.json" <<'PY'
import json
from pathlib import Path
import sys

directory = Path(sys.argv[1])
output = Path(sys.argv[2])
documents = []
for path in sorted(
    directory.glob("tag-object-*.json"),
    key=lambda item: int(item.stem.rsplit("-", 1)[1]),
):
    with path.open(encoding="utf-8") as handle:
        documents.append(json.load(handle))
with output.open("x", encoding="utf-8") as handle:
    json.dump(documents, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
PY

gh api "${api_headers[@]}" --paginate --slurp "repos/${repository}/actions/runs/${source_run_id}/artifacts?per_page=100" >"${temp_root}/source-artifacts.json"

gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${publisher_run_id}" >"${temp_root}/publisher-run.json"

publisher_run_attempt="$(
  python3 - "${temp_root}/publisher-run.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
attempt = document.get("run_attempt")
if type(attempt) is not int or attempt <= 0:
    raise SystemExit("publisher run attempt is missing or invalid")
print(attempt)
PY
)"

gh api "${api_headers[@]}" --paginate --slurp "repos/${repository}/actions/runs/${publisher_run_id}/attempts/${publisher_run_attempt}/jobs?per_page=100" >"${temp_root}/publisher-jobs.json"

gh api "${api_headers[@]}" --paginate --slurp "repos/${repository}/actions/runs/${publisher_run_id}/artifacts?per_page=100" >"${temp_root}/artifacts.json"

artifact_identity_file="${temp_root}/artifact-identity.txt"
python3 - "${temp_root}/source-run.json" "${temp_root}/publisher-run.json" "${temp_root}/artifacts.json" >"${artifact_identity_file}" <<'PY'
import json
import re
import sys

source_path, publisher_path, artifacts_path = sys.argv[1:]
with open(source_path, encoding="utf-8") as handle:
    source = json.load(handle)
with open(publisher_path, encoding="utf-8") as handle:
    publisher = json.load(handle)
with open(artifacts_path, encoding="utf-8") as handle:
    pages = json.load(handle)

source_id = source.get("id")
source_attempt = source.get("run_attempt")
publisher_id = publisher.get("id")
publisher_attempt = publisher.get("run_attempt")
for value, label in (
    (source_id, "source run id"),
    (source_attempt, "source run attempt"),
    (publisher_id, "publisher run id"),
    (publisher_attempt, "publisher run attempt"),
):
    if type(value) is not int or value <= 0:
        raise SystemExit(f"{label} is malformed")

expected = (
    f"validated-release-input-{publisher_id}-{publisher_attempt}-"
    f"{source_id}-{source_attempt}"
)
artifacts = []
if not isinstance(pages, list):
    raise SystemExit("artifact pagination response must be an array")
for page in pages:
    if not isinstance(page, dict) or not isinstance(page.get("artifacts"), list):
        raise SystemExit("artifact pagination page is malformed")
    artifacts.extend(page["artifacts"])

matches = [
    artifact
    for artifact in artifacts
    if isinstance(artifact, dict) and artifact.get("name") == expected
]
if len(matches) != 1:
    raise SystemExit(
        f"expected exactly one validator artifact named {expected!r}; found {len(matches)}"
    )

artifact = matches[0]
if artifact.get("expired") is not False:
    raise SystemExit("validator artifact is expired")
artifact_id = artifact.get("id")
artifact_digest = artifact.get("digest")
if type(artifact_id) is not int or artifact_id <= 0:
    raise SystemExit("validator artifact id is missing or invalid")
if (
    not isinstance(artifact_digest, str)
    or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest) is None
):
    raise SystemExit("validator artifact digest is missing or invalid")

print(artifact_id)
print(artifact_digest)
PY

readarray -t artifact_identity <"${artifact_identity_file}"
if (("${#artifact_identity[@]}" != 2)); then
  echo "Validator Artifact identity output was malformed." >&2
  exit 3
fi
artifact_id="${artifact_identity[0]}"
artifact_digest="${artifact_identity[1]}"

artifact_zip="${temp_root}/validator-artifact.zip"
gh api "${api_headers[@]}" "repos/${repository}/actions/artifacts/${artifact_id}/zip" >"${artifact_zip}"

python3 "${repo_root}/scripts/release/extract-runtime-proof-metadata.py" \
  --archive "${artifact_zip}" \
  --expected-digest "${artifact_digest}" \
  --output "${temp_root}/metadata.json" \
  --app-archive-digest-output "${temp_root}/archive-digest.txt"

read -r unsigned_archive_digest <"${temp_root}/archive-digest.txt"

source_artifact_identity_file="${temp_root}/source-artifact-identity.txt"
python3 - "${temp_root}/source-run.json" "${temp_root}/source-artifacts.json" >"${source_artifact_identity_file}" <<'PY'
import json
import re
import sys

source_path, artifacts_path = sys.argv[1:]
with open(source_path, encoding="utf-8") as handle:
    source = json.load(handle)
with open(artifacts_path, encoding="utf-8") as handle:
    pages = json.load(handle)

source_id = source.get("id")
source_attempt = source.get("run_attempt")
if type(source_id) is not int or source_id <= 0:
    raise SystemExit("source run id is malformed")
if type(source_attempt) is not int or source_attempt <= 0:
    raise SystemExit("source run attempt is malformed")

expected = f"unsigned-macos-release-{source_id}-{source_attempt}"
artifacts = []
if not isinstance(pages, list):
    raise SystemExit("source artifact pagination response must be an array")
for page in pages:
    if not isinstance(page, dict) or not isinstance(page.get("artifacts"), list):
        raise SystemExit("source artifact pagination page is malformed")
    artifacts.extend(page["artifacts"])

matches = [
    artifact
    for artifact in artifacts
    if isinstance(artifact, dict) and artifact.get("name") == expected
]
if len(matches) != 1:
    raise SystemExit(
        f"expected exactly one source artifact named {expected!r}; found {len(matches)}"
    )

artifact = matches[0]
if artifact.get("expired") is not False:
    raise SystemExit("source artifact is expired")
artifact_id = artifact.get("id")
artifact_digest = artifact.get("digest")
if type(artifact_id) is not int or artifact_id <= 0:
    raise SystemExit("source artifact id is missing or invalid")
if (
    not isinstance(artifact_digest, str)
    or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest) is None
):
    raise SystemExit("source artifact digest is missing or invalid")

print(artifact_id)
print(artifact_digest)
PY

readarray -t source_artifact_identity <"${source_artifact_identity_file}"
if (("${#source_artifact_identity[@]}" != 2)); then
  echo "Source Artifact identity output was malformed." >&2
  exit 3
fi
source_artifact_id="${source_artifact_identity[0]}"
source_artifact_digest="${source_artifact_identity[1]}"

source_artifact_zip="${temp_root}/source-artifact.zip"
gh api "${api_headers[@]}" "repos/${repository}/actions/artifacts/${source_artifact_id}/zip" >"${source_artifact_zip}"

python3 "${repo_root}/scripts/release/verify-runtime-proof-source-artifact.py" \
  --archive "${source_artifact_zip}" \
  --output "${temp_root}/source-artifact" \
  --expected-artifact-digest "${source_artifact_digest}" \
  --expected-app-archive-digest "${unsigned_archive_digest}"

readarray -t shas < <(
  python3 - "${temp_root}/source-run.json" "${temp_root}/publisher-run.json" <<'PY'
import json
import re
import sys

values = []
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    sha = document.get("head_sha")
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise SystemExit(f"workflow run has invalid head_sha: {path}")
    values.append(sha)
print("\n".join(values))
PY
)
source_sha="${shas[0]}"
publisher_sha="${shas[1]}"

gh api "${api_headers[@]}" "repos/${repository}/compare/${source_sha}...${publisher_sha}" >"${temp_root}/compare.json"

gh api "${api_headers[@]}" "repos/${repository}" >"${temp_root}/final-repository.json"

gh api "${api_headers[@]}" "repos/${repository}/commits/${encoded_default_branch}" >"${temp_root}/final-default-commit.json"

audit_args=(
  python3 "${repo_root}/scripts/release/audit-post-split-runtime-proof.py"
  --repository "${temp_root}/repository.json"
  --final-repository "${temp_root}/final-repository.json"
  --default-commit "${temp_root}/default-commit.json"
  --final-default-commit "${temp_root}/final-default-commit.json"
  --source-run "${temp_root}/source-run.json"
  --source-workflow "${temp_root}/source-workflow.json"
  --publisher-run "${temp_root}/publisher-run.json"
  --publisher-jobs "${temp_root}/publisher-jobs.json"
  --source-artifacts "${temp_root}/source-artifacts.json"
  --tag-ref "${temp_root}/tag-ref.json"
  --tag-objects "${temp_root}/tag-objects.json"
  --artifacts "${temp_root}/artifacts.json"
  --metadata "${temp_root}/metadata.json"
  --archive-digest "${unsigned_archive_digest}"
  --compare "${temp_root}/compare.json"
)
if [[ -n "${evidence_output}" ]]; then
  audit_args+=(--evidence-output "${evidence_output}")
fi
"${audit_args[@]}"
