#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  prove-post-split-ancestor-runtime.sh \
    --repository owner/disposable-repo \
    --confirm-disposable owner/disposable-repo \
    --source-ref REF \
    --tag vX.Y.Z \
    [--evidence-output post-split-proof.json]

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
evidence_output=""
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
    --evidence-output)
      evidence_output="${2:-}"
      if [[ -z "${evidence_output}" ]]; then
        echo "--evidence-output requires a non-empty path." >&2
        exit 2
      fi
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

for command_name in gh git python3; do
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

same_repository() {
  python3 - "$1" "$2" <<'PY'
import re
import sys

left, right = sys.argv[1:]
pattern = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
if pattern.fullmatch(left) is None or pattern.fullmatch(right) is None:
    raise SystemExit(1)
raise SystemExit(0 if left.casefold() == right.casefold() else 1)
PY
}

github_repository_from_remote() {
  python3 - "$1" <<'PY'
import re
import sys
from urllib.parse import urlparse

value = sys.argv[1].strip()
if not value:
    raise SystemExit(0)

path = None
scp = re.fullmatch(r"[^@]+@github\.com:(.+)", value, re.IGNORECASE)
if scp is not None:
    path = scp.group(1)
else:
    parsed = urlparse(value)
    if parsed.hostname is None or parsed.hostname.casefold() != "github.com":
        raise SystemExit(0)
    path = parsed.path.lstrip("/")

path = path.rstrip("/")
if path.endswith(".git"):
    path = path[:-4]
parts = path.split("/")
if len(parts) != 2 or any(
    re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None for part in parts
):
    raise SystemExit("GitHub origin URL does not resolve to owner/repo")
print("/".join(parts))
PY
}

if [[ -n "${GITHUB_REPOSITORY:-}" ]] &&
  same_repository "${GITHUB_REPOSITORY}" "${repository}"; then
  echo "This proof refuses the current repository from GITHUB_REPOSITORY. Use a separate disposable repository." >&2
  exit 2
fi

origin_url="$(git -C "${repo_root}" remote get-url origin 2>/dev/null || true)"
if [[ -n "${origin_url}" ]]; then
  if ! local_repository="$(github_repository_from_remote "${origin_url}")"; then
    echo "Unable to resolve the local GitHub origin safely: ${origin_url}" >&2
    exit 2
  fi
  if [[ -n "${local_repository}" ]] &&
    same_repository "${local_repository}" "${repository}"; then
    echo "This proof refuses the local checkout repository. Use a separate disposable repository." >&2
    exit 2
  fi
fi

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/post-split-proof-runner.XXXXXX")"
trap 'rm -rf "${temp_root}"' EXIT

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

urlencode() {
  python3 -c '
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
' "$1"
}

extract_sha() {
  python3 -c '
import json
import re
import sys

document = json.load(sys.stdin)
sha = document.get("sha")
if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("GitHub commit response has no canonical SHA")
print(sha)
'
}

repo_json="$(gh api "${api_headers[@]}" "repos/${repository}")"
default_branch="$(
  python3 -c '
import json
import sys

document = json.load(sys.stdin)
branch = document.get("default_branch")
if not isinstance(branch, str) or not branch:
    raise SystemExit("repository response has no default_branch")
print(branch)
' <<<"${repo_json}"
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
python3 -c '
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
' "${source_sha}" "${publisher_sha}" <<<"${compare_json}"

source_workflow_json="${temp_root}/source-release-build-workflow.json"
gh api "${api_headers[@]}" "repos/${repository}/contents/.github/workflows/${release_build_workflow}?ref=${source_sha}" >"${source_workflow_json}"
python3 "${repo_root}/scripts/release/validate-unprivileged-release-build-workflow.py" \
  --github-content-json "${source_workflow_json}"

gh api "${api_headers[@]}" "repos/${repository}/contents/.github/workflows/${release_publisher_workflow}?ref=${publisher_sha}" >/dev/null

if gh api "${api_headers[@]}" "repos/${repository}/git/ref/tags/${tag_name}" >/dev/null 2>&1; then
  echo "Stable proof tag already exists: ${tag_name}" >&2
  exit 3
fi

list_runs() {
  local workflow="$1"
  local event="$2"
  gh run list --repo "${repository}" --workflow "${workflow}" --event "${event}" --limit 100 --json databaseId,headBranch,headSha,status,conclusion
}

snapshot_run_ids() {
  local workflow="$1"
  local destination="$2"
  local encoded_workflow
  encoded_workflow="$(urlencode "${workflow}")"

  gh api "${api_headers[@]}" --paginate --slurp "repos/${repository}/actions/workflows/${encoded_workflow}/runs?per_page=100" |
    python3 -c '
import json
import sys

pages = json.load(sys.stdin)
if not isinstance(pages, list) or not pages:
    raise SystemExit("workflow-run baseline pagination response must be a non-empty array")

runs = []
declared_total = None
for page in pages:
    if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
        raise SystemExit("workflow-run baseline page is malformed")
    total_count = page.get("total_count")
    if type(total_count) is not int or total_count < 0:
        raise SystemExit("workflow-run baseline total_count is malformed")
    if declared_total is None:
        declared_total = total_count
    elif total_count != declared_total:
        raise SystemExit("workflow-run baseline pages disagree on total_count")
    runs.extend(page["workflow_runs"])

if declared_total != len(runs):
    raise SystemExit(
        f"workflow-run baseline total_count={declared_total} does not match "
        f"fetched entries={len(runs)}"
    )

ids = []
seen = set()
for item in runs:
    if not isinstance(item, dict):
        raise SystemExit("workflow-run baseline entry must be an object")
    run_id = item.get("id")
    if type(run_id) is not int or run_id <= 0:
        raise SystemExit("workflow-run baseline entry has invalid id")
    if run_id in seen:
        raise SystemExit(f"workflow-run baseline contains duplicate id: {run_id}")
    seen.add(run_id)
    ids.append(run_id)

json.dump(sorted(ids), sys.stdout, separators=(",", ":"))
sys.stdout.write("\n")
' >"${destination}"
}

source_baseline="${temp_root}/source-baseline.json"
publisher_baseline="${temp_root}/publisher-baseline.json"
snapshot_run_ids "${release_build_workflow}" "${source_baseline}"
snapshot_run_ids "${release_publisher_workflow}" "${publisher_baseline}"

gh api "${api_headers[@]}" --method POST "repos/${repository}/git/refs" -f "ref=refs/tags/${tag_name}" -f "sha=${source_sha}" >/dev/null

find_source_run_id() {
  local attempt list_json run_id
  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    list_json="$(list_runs "${release_build_workflow}" push)"
    run_id="$(
      python3 -c '
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
' "${tag_name}" "${source_sha}" "${source_baseline}" <<<"${list_json}"
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
      python3 -c '
import json
import sys

document = json.load(sys.stdin)
status = document.get("status")
conclusion = document.get("conclusion")
print(
    status if isinstance(status, str) else "",
    conclusion if isinstance(conclusion, str) else "",
)
' <<<"${run_json}"
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
  python3 -c '
import json
import sys

document = json.load(sys.stdin)
attempt = document.get("run_attempt")
if type(attempt) is not int or attempt <= 0:
    raise SystemExit("Release Build run_attempt is missing or malformed")
print(attempt)
' <<<"${source_run_json}"
)"

find_publisher_run_id() {
  local attempt list_json candidate_ids candidate_id run_json run_attempt artifact_json matched
  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    list_json="$(list_runs "${release_publisher_workflow}" workflow_run)"
    candidate_ids="$(
      python3 -c '
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
' "${default_branch}" "${publisher_sha}" "${publisher_baseline}" <<<"${list_json}"
    )"

    matched=""
    while IFS= read -r candidate_id; do
      [[ -n "${candidate_id}" ]] || continue
      run_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${candidate_id}")"
      run_attempt="$(
        python3 -c '
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
' <<<"${run_json}"
      )" || continue

      artifact_json="$(gh api "${api_headers[@]}" --paginate --slurp "repos/${repository}/actions/runs/${candidate_id}/artifacts?per_page=100")"
      if python3 -c '
import json
import sys

publisher_id, publisher_attempt, source_id, source_attempt = map(int, sys.argv[1:])
pages = json.load(sys.stdin)
if not isinstance(pages, list):
    raise SystemExit(1)
artifacts = []
declared_total = None
for page in pages:
    if not isinstance(page, dict) or not isinstance(page.get("artifacts"), list):
        raise SystemExit(1)
    total_count = page.get("total_count")
    if type(total_count) is not int or total_count < 0:
        raise SystemExit(1)
    if declared_total is None:
        declared_total = total_count
    elif declared_total != total_count:
        raise SystemExit(1)
    artifacts.extend(page["artifacts"])
if declared_total is None or declared_total != len(artifacts):
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
' "${candidate_id}" "${run_attempt}" "${source_run_id}" "${source_run_attempt}" <<<"${artifact_json}"; then
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

wait_for_publisher_validation_success() {
  local run_id="$1"
  local run_json run_attempt attempt jobs_json validation_state

  run_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${run_id}")"
  run_attempt="$(
    python3 -c '
import json
import sys

document = json.load(sys.stdin)
attempt = document.get("run_attempt")
if document.get("event") != "workflow_run":
    raise SystemExit("Release Publisher event is not workflow_run")
if type(attempt) is not int or attempt <= 0:
    raise SystemExit("Release Publisher run_attempt is missing or malformed")
print(attempt)
' <<<"${run_json}"
  )"

  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    jobs_json="$(gh api "${api_headers[@]}" --paginate --slurp "repos/${repository}/actions/runs/${run_id}/attempts/${run_attempt}/jobs?per_page=100")"
    validation_state="$(
      python3 -c '
import json
import sys

run_id = int(sys.argv[1])
publisher_sha, default_branch = sys.argv[2:]
pages = json.load(sys.stdin)
if not isinstance(pages, list):
    print("FAIL:publisher job pagination response must be an array")
    raise SystemExit(0)

jobs = []
declared_total = None
for page in pages:
    if not isinstance(page, dict) or not isinstance(page.get("jobs"), list):
        print("FAIL:publisher job pagination page is malformed")
        raise SystemExit(0)
    total_count = page.get("total_count")
    if type(total_count) is not int or total_count < 0:
        print("FAIL:publisher job total_count is malformed")
        raise SystemExit(0)
    if declared_total is None:
        declared_total = total_count
    elif declared_total != total_count:
        print("FAIL:publisher job pages disagree on total_count")
        raise SystemExit(0)
    jobs.extend(page["jobs"])

if declared_total is None or declared_total != len(jobs):
    print("FAIL:publisher job pagination total_count does not match collected jobs")
    raise SystemExit(0)

matches = [
    job
    for job in jobs
    if isinstance(job, dict)
    and job.get("name") == "Validate release input without secrets"
]
if not matches:
    print("WAIT")
    raise SystemExit(0)
if len(matches) != 1:
    print(f"FAIL:expected exactly one publisher validation job; found {len(matches)}")
    raise SystemExit(0)

job = matches[0]
checks = (
    (job.get("run_id") == run_id, "validation job run_id does not match publisher run"),
    (job.get("head_sha") == publisher_sha, "validation job head_sha does not match publisher SHA"),
    (job.get("workflow_name") == "Release Publisher", "validation job workflow_name does not match Release Publisher"),
    (job.get("head_branch") == default_branch, "validation job head_branch does not match default branch"),
)
for ok, message in checks:
    if not ok:
        print(f"FAIL:{message}")
        raise SystemExit(0)

status = job.get("status")
conclusion = job.get("conclusion")
if status == "completed":
    if conclusion == "success":
        print("SUCCESS")
    else:
        print(f"FAIL:publisher validation job concluded {conclusion!r}")
else:
    print("WAIT")
' "${run_id}" "${publisher_sha}" "${default_branch}" <<<"${jobs_json}"
    )"

    case "${validation_state}" in
      SUCCESS)
        return 0
        ;;
      WAIT)
        sleep "${poll_seconds}"
        ;;
      FAIL:*)
        echo "${validation_state#FAIL:}" >&2
        return 1
        ;;
      *)
        echo "Publisher validation job state output was malformed: ${validation_state}" >&2
        return 1
        ;;
    esac
  done

  echo "Release Publisher validation job did not succeed within the proof polling window." >&2
  return 1
}

publisher_run_id="$(find_publisher_run_id)"
wait_for_publisher_validation_success "${publisher_run_id}"

audit_args=(
  bash "${repo_root}/scripts/release/audit-post-split-runtime-proof.sh"
  "${repository}"
  "${source_run_id}"
  "${publisher_run_id}"
)
if [[ -n "${evidence_output}" ]]; then
  audit_args+=(--evidence-output "${evidence_output}")
fi
"${audit_args[@]}"

printf 'post-split ancestor proof passed: repository=%s tag=%s source_run_id=%s publisher_run_id=%s\n' "${repository}" "${tag_name}" "${source_run_id}" "${publisher_run_id}"
