#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  prove-post-split-ancestor-runtime.sh \
    --repository owner/disposable-repo \
    --confirm-disposable owner/disposable-repo \
    --source-ref REF \
    --tag vX.Y.Z

Creates one stable release tag in a disposable repository, waits for the
secret-free Release Build and downstream Release Publisher, then delegates to
audit-post-split-runtime-proof.sh for the read-only control-code proof.

The stable tag is intentionally not deleted. A correct immutable v* Ruleset may
forbid deletion, and the tag/run pair is useful audit evidence.
EOF
}

repository=""
confirmed_repository=""
source_ref=""
tag_name=""
release_build_workflow="release-build.yml"
release_publisher_workflow="release-publisher.yml"

while (($#)); do
  case "$1" in
    --repository)
      repository="${2:-}"
      shift 2
      ;;
    --confirm-disposable)
      confirmed_repository="${2:-}"
      shift 2
      ;;
    --source-ref)
      source_ref="${2:-}"
      shift 2
      ;;
    --tag)
      tag_name="${2:-}"
      shift 2
      ;;
    --release-build-workflow)
      release_build_workflow="${2:-}"
      shift 2
      ;;
    --release-publisher-workflow)
      release_publisher_workflow="${2:-}"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "--repository must be owner/repo." >&2
  exit 2
fi
if [[ "${confirmed_repository}" != "${repository}" ]]; then
  echo "--confirm-disposable must exactly equal --repository." >&2
  exit 2
fi
if [[ -n "${GITHUB_REPOSITORY:-}" && "${GITHUB_REPOSITORY}" == "${repository}" ]]; then
  echo "This proof refuses the current repository. Use a separate disposable repository." >&2
  exit 2
fi
if [[ -z "${source_ref}" || ! "${source_ref}" =~ ^[A-Za-z0-9._/-]+$ ]]; then
  echo "--source-ref must be a non-empty Git ref or commit using safe ref characters." >&2
  exit 2
fi
if [[ ! "${tag_name}" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  echo "--tag must be a canonical stable SemVer tag such as v0.0.1." >&2
  exit 2
fi
for workflow in "${release_build_workflow}" "${release_publisher_workflow}"; do
  if [[ ! "${workflow}" =~ ^[A-Za-z0-9_.-]+\.ya?ml$ ]]; then
    echo "Workflow arguments must be workflow filenames such as release-build.yml." >&2
    exit 2
  fi
done

for command_name in gh python3; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

poll_attempts="${PROOF_POLL_ATTEMPTS:-60}"
poll_seconds="${PROOF_POLL_SECONDS:-5}"
if [[ ! "${poll_attempts}" =~ ^[1-9][0-9]*$ ]] || [[ ! "${poll_seconds}" =~ ^[0-9]+$ ]]; then
  echo "PROOF_POLL_ATTEMPTS must be positive and PROOF_POLL_SECONDS non-negative." >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
temp_root="$(mktemp -d "${TMPDIR:-/tmp}/post-split-proof-runner.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

urlencode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
}

extract_sha() {
  python3 - <<'PY'
import json
import re
import sys

document = json.load(sys.stdin)
sha = document.get("sha")
if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("GitHub commit response has no canonical SHA")
print(sha)
PY
}

repo_json="$(gh api "${api_headers[@]}" "repos/${repository}")"
default_branch="$(
  python3 - <<'PY' <<<"${repo_json}"
import json
import sys

document = json.load(sys.stdin)
branch = document.get("default_branch")
if not isinstance(branch, str) or not branch:
    raise SystemExit("repository response has no default_branch")
print(branch)
PY
)"

encoded_default_branch="$(urlencode "${default_branch}")"
encoded_source_ref="$(urlencode "${source_ref}")"

publisher_commit_json="$(gh api "${api_headers[@]}" "repos/${repository}/commits/${encoded_default_branch}")"
publisher_sha="$(extract_sha <<<"${publisher_commit_json}")"

source_commit_json="$(gh api "${api_headers[@]}" "repos/${repository}/commits/${encoded_source_ref}")"
source_sha="$(extract_sha <<<"${source_commit_json}")"

if [[ "${source_sha}" == "${publisher_sha}" ]]; then
  echo "--source-ref must resolve to a strict ancestor, not the current default-branch head." >&2
  exit 3
fi

compare_json="$(gh api "${api_headers[@]}" "repos/${repository}/compare/${source_sha}...${publisher_sha}")"
python3 - "${source_sha}" "${publisher_sha}" <<'PY' <<<"${compare_json}"
import json
import sys

source_sha, publisher_sha = sys.argv[1:]
document = json.load(sys.stdin)
if document.get("status") != "ahead":
    raise SystemExit("source ref is not a strict ancestor of current default-branch head")
ahead_by = document.get("ahead_by")
behind_by = document.get("behind_by")
if type(ahead_by) is not int or ahead_by <= 0 or behind_by != 0:
    raise SystemExit("source/default comparison is not a strict ancestor relation")
merge_base = document.get("merge_base_commit")
if not isinstance(merge_base, dict) or merge_base.get("sha") != source_sha:
    raise SystemExit("source SHA is not the merge base of the current default branch")
if publisher_sha == source_sha:
    raise SystemExit("source and publisher SHAs must differ")
PY

gh api "${api_headers[@]}"   "repos/${repository}/contents/.github/workflows/${release_build_workflow}?ref=${source_sha}" >/dev/null
gh api "${api_headers[@]}"   "repos/${repository}/contents/.github/workflows/${release_publisher_workflow}?ref=${publisher_sha}" >/dev/null

if gh api "${api_headers[@]}" "repos/${repository}/git/ref/tags/${tag_name}" >/dev/null 2>&1; then
  echo "Stable proof tag already exists: ${tag_name}" >&2
  exit 3
fi

list_runs() {
  local workflow="$1"
  local event="$2"
  gh run list     --repo "${repository}"     --workflow "${workflow}"     --event "${event}"     --limit 100     --json databaseId,headBranch,headSha,status,conclusion
}

snapshot_run_ids() {
  local workflow="$1"
  local event="$2"
  local destination="$3"
  list_runs "${workflow}" "${event}" |
    python3 -c '
import json
import sys

runs = json.load(sys.stdin)
ids = sorted(
    item.get("databaseId")
    for item in runs
    if isinstance(item, dict)
    and type(item.get("databaseId")) is int
    and item.get("databaseId") > 0
)
json.dump(ids, sys.stdout, separators=(",", ":"))
sys.stdout.write("\n")
' >"${destination}"
}

source_baseline="${temp_root}/source-baseline.json"
publisher_baseline="${temp_root}/publisher-baseline.json"
snapshot_run_ids "${release_build_workflow}" push "${source_baseline}"
snapshot_run_ids "${release_publisher_workflow}" workflow_run "${publisher_baseline}"

gh api "${api_headers[@]}"   --method POST   "repos/${repository}/git/refs"   -f "ref=refs/tags/${tag_name}"   -f "sha=${source_sha}" >/dev/null

find_source_run_id() {
  local attempt list_json run_id
  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    list_json="$(list_runs "${release_build_workflow}" push)"
    run_id="$(
      python3 - "${tag_name}" "${source_sha}" "${source_baseline}" <<'PY' <<<"${list_json}"
import json
import sys

tag, source_sha, baseline_path = sys.argv[1:]
runs = json.load(sys.stdin)
with open(baseline_path, encoding="utf-8") as handle:
    baseline = set(json.load(handle))

matches = [
    item.get("databaseId")
    for item in runs
    if isinstance(item, dict)
    and item.get("headBranch") == tag
    and item.get("headSha") == source_sha
    and type(item.get("databaseId")) is int
    and item.get("databaseId") > 0
    and item.get("databaseId") not in baseline
]
if len(matches) == 1:
    print(matches[0])
elif len(matches) > 1:
    raise SystemExit(f"multiple fresh Release Build runs matched the proof tag: {matches!r}")
PY
    )" || return 1
    if [[ "${run_id}" =~ ^[1-9][0-9]*$ ]]; then
      printf '%s\n' "${run_id}"
      return 0
    fi
    sleep "${poll_seconds}"
  done
  echo "Unable to locate the fresh Release Build run for ${tag_name}." >&2
  return 1
}

wait_for_run_completion() {
  local run_id="$1"
  local require_success="$2"
  local attempt run_json status conclusion
  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    run_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${run_id}")"
    read -r status conclusion < <(
      python3 - <<'PY' <<<"${run_json}"
import json
import sys

document = json.load(sys.stdin)
status = document.get("status")
conclusion = document.get("conclusion")
print(
    status if isinstance(status, str) else "",
    conclusion if isinstance(conclusion, str) else "",
)
PY
    )
    if [[ "${status}" == completed ]]; then
      if [[ "${require_success}" == true && "${conclusion}" != success ]]; then
        echo "Workflow run ${run_id} completed with conclusion '${conclusion}', expected success." >&2
        return 1
      fi
      printf '%s\n' "${conclusion}"
      return 0
    fi
    sleep "${poll_seconds}"
  done
  echo "Workflow run ${run_id} did not complete within the proof polling window." >&2
  return 1
}

source_run_id="$(find_source_run_id)"
wait_for_run_completion "${source_run_id}" true >/dev/null

source_run_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${source_run_id}")"
source_run_attempt="$(
  python3 - <<'PY' <<<"${source_run_json}"
import json
import sys

document = json.load(sys.stdin)
attempt = document.get("run_attempt")
if type(attempt) is not int or attempt <= 0:
    raise SystemExit("Release Build run_attempt is missing or malformed")
print(attempt)
PY
)"

find_publisher_run_id() {
  local attempt list_json candidate_ids candidate_id run_json run_attempt artifact_json matched
  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    list_json="$(list_runs "${release_publisher_workflow}" workflow_run)"
    candidate_ids="$(
      python3 - "${default_branch}" "${publisher_sha}" "${publisher_baseline}" <<'PY' <<<"${list_json}"
import json
import sys

default_branch, publisher_sha, baseline_path = sys.argv[1:]
runs = json.load(sys.stdin)
with open(baseline_path, encoding="utf-8") as handle:
    baseline = set(json.load(handle))

matches = [
    item.get("databaseId")
    for item in runs
    if isinstance(item, dict)
    and item.get("headBranch") == default_branch
    and item.get("headSha") == publisher_sha
    and type(item.get("databaseId")) is int
    and item.get("databaseId") > 0
    and item.get("databaseId") not in baseline
]
print("\n".join(str(item) for item in matches))
PY
    )"

    matched=""
    while IFS= read -r candidate_id; do
      [[ -n "${candidate_id}" ]] || continue
      run_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${candidate_id}")"
      run_attempt="$(
        python3 - <<'PY' <<<"${run_json}"
import json
import sys

document = json.load(sys.stdin)
attempt = document.get("run_attempt")
event = document.get("event")
if event != "workflow_run":
    raise SystemExit(1)
if type(attempt) is not int or attempt <= 0:
    raise SystemExit(1)
print(attempt)
PY
      )" || continue

      artifact_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${candidate_id}/artifacts?per_page=100")"
      if python3 - "${candidate_id}" "${run_attempt}" "${source_run_id}" "${source_run_attempt}" <<'PY' <<<"${artifact_json}"
import json
import sys

publisher_id, publisher_attempt, source_id, source_attempt = map(int, sys.argv[1:])
document = json.load(sys.stdin)
artifacts = document.get("artifacts")
if not isinstance(artifacts, list):
    raise SystemExit(1)
expected = (
    f"validated-release-input-{publisher_id}-{publisher_attempt}-"
    f"{source_id}-{source_attempt}"
)
matches = [
    item
    for item in artifacts
    if isinstance(item, dict)
    and item.get("name") == expected
    and item.get("expired") is False
]
raise SystemExit(0 if len(matches) == 1 else 1)
PY
      then
        if [[ -n "${matched}" ]]; then
          echo "Multiple fresh Release Publisher runs contain validator artifacts for source run ${source_run_id}." >&2
          return 1
        fi
        matched="${candidate_id}"
      fi
    done <<<"${candidate_ids}"

    if [[ "${matched}" =~ ^[1-9][0-9]*$ ]]; then
      printf '%s\n' "${matched}"
      return 0
    fi
    sleep "${poll_seconds}"
  done

  echo "Unable to locate a Release Publisher validator artifact for source run ${source_run_id}." >&2
  return 1
}

publisher_run_id="$(find_publisher_run_id)"
wait_for_run_completion "${publisher_run_id}" false >/dev/null

bash "${repo_root}/scripts/release/audit-post-split-runtime-proof.sh"   "${repository}"   "${source_run_id}"   "${publisher_run_id}"

printf 'post-split ancestor proof passed: repository=%s tag=%s source_run_id=%s publisher_run_id=%s\n'   "${repository}" "${tag_name}" "${source_run_id}" "${publisher_run_id}"
