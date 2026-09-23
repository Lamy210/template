#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: audit-post-split-runtime-proof.sh owner/repo SOURCE_RUN_ID PUBLISHER_RUN_ID

Read-only audit for a disposable-repository two-stage release proof.
Run it immediately after the proof while the publisher workflow SHA is still
the repository default-branch head.
EOF
}

repository="${1:-}"
source_run_id="${2:-}"
publisher_run_id="${3:-}"
if [[ ! "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] ||
  [[ ! "${source_run_id}" =~ ^[1-9][0-9]*$ ]] ||
  [[ ! "${publisher_run_id}" =~ ^[1-9][0-9]*$ ]] ||
  (($# != 3)); then
  usage
  exit 2
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

gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${publisher_run_id}" >"${temp_root}/publisher-run.json"

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
  --output "${temp_root}/metadata.json"

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

python3 "${repo_root}/scripts/release/audit-post-split-runtime-proof.py" --repository "${temp_root}/repository.json" --default-commit "${temp_root}/default-commit.json" --source-run "${temp_root}/source-run.json" --publisher-run "${temp_root}/publisher-run.json" --artifacts "${temp_root}/artifacts.json" --metadata "${temp_root}/metadata.json" --compare "${temp_root}/compare.json"
