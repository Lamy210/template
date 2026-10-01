#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common/repository-name.sh
source "${script_dir}/../common/repository-name.sh"

usage() {
  cat >&2 <<'EOF'
Usage:
  prove-release-environment-policy.sh \
    --repository owner/disposable-repo \
    --confirm-disposable owner/disposable-repo

The disposable repository must already contain:
  .github/workflows/release-environment-proof.yml

That workflow is copied from examples/release-environment-proof.yml and is
intentionally secret-free. This proof first requires the repository default
branch to enter the release Environment successfully, then creates temporary
branch/tag refs and requires those unauthorized refs to be denied.
EOF
}

repository=""
confirmed_repository=""
workflow_name="release-environment-proof.yml"

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
    --workflow)
      workflow_name="${2:-}"
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

if ! is_canonical_repository_name "${repository}"; then
  echo "--repository must use canonical owner/repo form." >&2
  exit 2
fi
if [[ "${confirmed_repository}" != "${repository}" ]]; then
  echo "--confirm-disposable must exactly equal --repository." >&2
  exit 2
fi
if [[ ! "${workflow_name}" =~ ^[A-Za-z0-9_.-]+\.ya?ml$ ]]; then
  echo "--workflow must be a workflow filename such as release-environment-proof.yml." >&2
  exit 2
fi

if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  echo "Refusing destructive disposable-repository proof from GitHub Actions; run from a trusted local operator session." >&2
  exit 2
fi

for command_name in gh git python3; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

same_repository() {
  python3 - "$1" "$2" <<'PY'
import sys

left, right = sys.argv[1:]
raise SystemExit(0 if left.casefold() == right.casefold() else 1)
PY
}

github_repository_from_remote() {
  python3 "${repo_root}/scripts/common/resolve-github-repository-from-remote.py" "$1"
}

if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
  if ! is_canonical_repository_name "${GITHUB_REPOSITORY}"; then
    echo "GITHUB_REPOSITORY must use canonical owner/repo form before disposable proof." >&2
    exit 2
  fi
  if same_repository "${GITHUB_REPOSITORY}" "${repository}"; then
    echo "This proof refuses the current repository from GITHUB_REPOSITORY. Use a separate disposable repository." >&2
    exit 2
  fi
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

nonce="${PROOF_NONCE:-$(date -u +%Y%m%d%H%M%S)-$$}"
if [[ ! "${nonce}" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "PROOF_NONCE must contain only letters, numbers, dot, underscore, or hyphen." >&2
  exit 2
fi

poll_attempts="${PROOF_POLL_ATTEMPTS:-30}"
poll_seconds="${PROOF_POLL_SECONDS:-2}"
if [[ ! "${poll_attempts}" =~ ^[1-9][0-9]*$ ]] || [[ ! "${poll_seconds}" =~ ^[0-9]+$ ]]; then
  echo "PROOF_POLL_ATTEMPTS must be positive and PROOF_POLL_SECONDS non-negative." >&2
  exit 2
fi

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

repo_json="$(gh api "${api_headers[@]}" "repos/${repository}")"
readarray -t repository_identity < <(
  python3 -c '
import json
import re
import sys

document = json.load(sys.stdin)
repository_id = document.get("id")
full_name = document.get("full_name")
branch = document.get("default_branch")
if type(repository_id) is not int or repository_id <= 0:
    raise SystemExit("repository response has no valid id")
if not isinstance(full_name, str) or re.fullmatch(
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
    full_name,
) is None:
    raise SystemExit("repository response has no canonical full_name")
if not isinstance(branch, str) or not branch:
    raise SystemExit("repository response has no default_branch")
print(repository_id)
print(full_name)
print(branch)
' <<<"${repo_json}"
)
if (("${#repository_identity[@]}" != 3)); then
  echo "Repository identity output was malformed." >&2
  exit 3
fi
repository_id="${repository_identity[0]}"
repository_full_name="${repository_identity[1]}"
default_branch="${repository_identity[2]}"

if ! same_repository "${repository_full_name}" "${repository}"; then
  echo "Repository API identity does not match --repository: ${repository_full_name}" >&2
  exit 3
fi

encoded_default_branch="$(urlencode "${default_branch}")"
commit_json="$(gh api "${api_headers[@]}" "repos/${repository}/commits/${encoded_default_branch}")"
default_sha="$(
  python3 -c '
import json
import re
import sys

document = json.load(sys.stdin)
sha = document.get("sha")
if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("default branch response has no canonical commit SHA")
print(sha)
' <<<"${commit_json}"
)"

gh api "${api_headers[@]}" "repos/${repository}/contents/.github/workflows/${workflow_name}?ref=${default_sha}" |
  python3 "${repo_root}/scripts/release/validate-release-environment-proof-workflow.py" --expected-path ".github/workflows/${workflow_name}" --trusted-workflow "${repo_root}/examples/release-environment-proof.yml"

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/release-environment-proof.XXXXXX")"
branch_name="environment-proof/${nonce}"
tag_name="environment-proof-${nonce}"
branch_created=false
tag_created=false

cleanup_best_effort() {
  rm -rf "${temp_root}"
  if [[ "${branch_created}" == true ]]; then
    if gh api "${api_headers[@]}" --method DELETE "repos/${repository}/git/refs/heads/${branch_name}" >/dev/null 2>&1; then
      branch_created=false
    fi
  fi
  if [[ "${tag_created}" == true ]]; then
    if gh api "${api_headers[@]}" --method DELETE "repos/${repository}/git/refs/tags/${tag_name}" >/dev/null 2>&1; then
      tag_created=false
    fi
  fi
}

cleanup_refs_strict() {
  local failed=false

  if [[ "${branch_created}" == true ]]; then
    if gh api "${api_headers[@]}" --method DELETE "repos/${repository}/git/refs/heads/${branch_name}" >/dev/null; then
      branch_created=false
    else
      echo "Failed to delete temporary proof branch: ${branch_name}" >&2
      failed=true
    fi
  fi

  if [[ "${tag_created}" == true ]]; then
    if gh api "${api_headers[@]}" --method DELETE "repos/${repository}/git/refs/tags/${tag_name}" >/dev/null; then
      tag_created=false
    else
      echo "Failed to delete temporary proof tag: ${tag_name}" >&2
      failed=true
    fi
  fi

  [[ "${failed}" == false ]]
}

trap cleanup_best_effort EXIT

if gh api "${api_headers[@]}" "repos/${repository}/git/ref/heads/${branch_name}" >/dev/null 2>&1; then
  echo "Temporary branch already exists: ${branch_name}" >&2
  exit 3
fi
if gh api "${api_headers[@]}" "repos/${repository}/git/ref/tags/${tag_name}" >/dev/null 2>&1; then
  echo "Temporary tag already exists: ${tag_name}" >&2
  exit 3
fi

gh api "${api_headers[@]}" --method POST "repos/${repository}/git/refs" -f "ref=refs/heads/${branch_name}" -f "sha=${default_sha}" >/dev/null
branch_created=true

gh api "${api_headers[@]}" --method POST "repos/${repository}/git/refs" -f "ref=refs/tags/${tag_name}" -f "sha=${default_sha}" >/dev/null
tag_created=true

list_workflow_runs() {
  local encoded_workflow
  encoded_workflow="$(urlencode "${workflow_name}")"

  gh api "${api_headers[@]}" --paginate --slurp \
    "repos/${repository}/actions/workflows/${encoded_workflow}/runs?event=workflow_dispatch&per_page=100" |
    python3 -c '
import json
import re
import sys

pages = json.load(sys.stdin)
if not isinstance(pages, list) or not pages:
    raise SystemExit("workflow-run pagination response must be a non-empty array")

runs = []
declared_total = None
for page in pages:
    if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
        raise SystemExit("workflow-run pagination page is malformed")
    total_count = page.get("total_count")
    if type(total_count) is not int or total_count < 0:
        raise SystemExit("workflow-run total_count is malformed")
    if declared_total is None:
        declared_total = total_count
    elif total_count != declared_total:
        raise SystemExit("workflow-run pages disagree on total_count")
    runs.extend(page["workflow_runs"])

if declared_total != len(runs):
    raise SystemExit(
        f"workflow-run total_count={declared_total} does not match "
        f"fetched entries={len(runs)}"
    )

normalized = []
seen = set()
for item in runs:
    if not isinstance(item, dict):
        raise SystemExit("workflow-run entry must be an object")
    run_id = item.get("id")
    title = item.get("display_title")
    head_branch = item.get("head_branch")
    head_sha = item.get("head_sha")
    event = item.get("event")
    if type(run_id) is not int or run_id <= 0:
        raise SystemExit("workflow-run entry has invalid id")
    if run_id in seen:
        raise SystemExit(f"workflow-run response contains duplicate id: {run_id}")
    seen.add(run_id)
    if not isinstance(title, str) or not title:
        raise SystemExit(f"workflow-run entry {run_id} has invalid display_title")
    if not isinstance(head_branch, str) or not head_branch:
        raise SystemExit(f"workflow-run entry {run_id} has invalid head_branch")
    if (
        not isinstance(head_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None
    ):
        raise SystemExit(f"workflow-run entry {run_id} has invalid head_sha")
    if event != "workflow_dispatch":
        raise SystemExit(
            f"workflow-run entry {run_id} event={event!r}, expected 'workflow_dispatch'"
        )
    normalized.append(
        {
            "databaseId": run_id,
            "displayTitle": title,
            "headBranch": head_branch,
            "headSha": head_sha,
        }
    )

json.dump(normalized, sys.stdout, separators=(",", ":"))
sys.stdout.write("\n")
'
}

snapshot_run_ids() {
  local destination="$1"
  list_workflow_runs |
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

find_run_id() {
  local title="$1"
  local expected_ref="$2"
  local expected_sha="$3"
  local baseline_run_ids="$4"
  local attempt list_json run_id
  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    list_json="$(list_workflow_runs)"
    run_id="$(
      python3 -c '
import json
import sys

title, expected_ref, expected_sha, baseline_path = sys.argv[1:]
runs = json.load(sys.stdin)
with open(baseline_path, encoding="utf-8") as handle:
    baseline = set(json.load(handle))

matches = [
    item.get("databaseId")
    for item in runs
    if isinstance(item, dict)
    and item.get("displayTitle") == title
    and item.get("headBranch") == expected_ref
    and item.get("headSha") == expected_sha
    and type(item.get("databaseId")) is int
    and item.get("databaseId") > 0
    and item.get("databaseId") not in baseline
]
if len(matches) == 1:
    print(matches[0])
elif len(matches) > 1:
    raise SystemExit(
        f"multiple fresh workflow runs matched title={title!r} ref={expected_ref!r}: {matches!r}"
    )
' "${title}" "${expected_ref}" "${expected_sha}" "${baseline_run_ids}" <<<"${list_json}"
    )" || return 1
    if [[ "${run_id}" =~ ^[1-9][0-9]*$ ]]; then
      printf '%s\n' "${run_id}"
      return 0
    fi
    sleep "${poll_seconds}"
  done
  echo "Unable to locate fresh dispatched workflow run: ${title} ref=${expected_ref}" >&2
  return 1
}

wait_for_completion() {
  local run_id="$1"
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
      printf '%s\n' "${conclusion}"
      return 0
    fi
    sleep "${poll_seconds}"
  done
  echo "Workflow run ${run_id} did not complete within proof polling window." >&2
  return 1
}

list_run_jobs() {
  local run_id="$1"

  gh api "${api_headers[@]}" --paginate --slurp \
    "repos/${repository}/actions/runs/${run_id}/jobs?per_page=100" |
    python3 -c '
import json
import sys

pages = json.load(sys.stdin)
if not isinstance(pages, list) or not pages:
    raise SystemExit("workflow jobs pagination response must be a non-empty array")

jobs = []
declared_total = None
for page in pages:
    if not isinstance(page, dict) or not isinstance(page.get("jobs"), list):
        raise SystemExit("workflow jobs pagination page is malformed")
    total_count = page.get("total_count")
    if type(total_count) is not int or total_count < 0:
        raise SystemExit("workflow jobs total_count is malformed")
    if declared_total is None:
        declared_total = total_count
    elif total_count != declared_total:
        raise SystemExit("workflow jobs pages disagree on total_count")
    jobs.extend(page["jobs"])

if declared_total != len(jobs):
    raise SystemExit(
        f"workflow jobs total_count={declared_total} does not match "
        f"fetched entries={len(jobs)}"
    )

normalized = []
seen = set()
for item in jobs:
    if not isinstance(item, dict):
        raise SystemExit("workflow job entry must be an object")
    job_id = item.get("id")
    name = item.get("name")
    status = item.get("status")
    conclusion = item.get("conclusion")
    if type(job_id) is not int or job_id <= 0:
        raise SystemExit("workflow job entry has invalid id")
    if job_id in seen:
        raise SystemExit(f"workflow jobs response contains duplicate id: {job_id}")
    seen.add(job_id)
    if not isinstance(name, str) or not name:
        raise SystemExit(f"workflow job entry {job_id} has invalid name")
    if not isinstance(status, str) or not status:
        raise SystemExit(f"workflow job entry {job_id} has invalid status")
    if conclusion is not None and not isinstance(conclusion, str):
        raise SystemExit(f"workflow job entry {job_id} has invalid conclusion")
    normalized.append(
        {
            "id": job_id,
            "name": name,
            "status": status,
            "conclusion": conclusion,
        }
    )

json.dump(normalized, sys.stdout, separators=(",", ":"))
sys.stdout.write("\n")
'
}

assert_allowed_jobs() {
  local run_id="$1"
  local jobs_json
  jobs_json="$(list_run_jobs "${run_id}")"
  python3 -c '
import json
import sys

jobs = json.load(sys.stdin)
if not isinstance(jobs, list):
    raise SystemExit("workflow jobs response is malformed")

by_name = {
    job.get("name"): job
    for job in jobs
    if isinstance(job, dict) and isinstance(job.get("name"), str)
}
baseline = by_name.get("Baseline runner")
probe = by_name.get("Release environment probe")
if not isinstance(baseline, dict) or baseline.get("conclusion") != "success":
    raise SystemExit("baseline job must succeed before treating the proof as meaningful")
if not isinstance(probe, dict) or probe.get("conclusion") != "success":
    raise SystemExit("release Environment probe job must succeed for the authorized default branch")
' <<<"${jobs_json}"
}

assert_denied_jobs() {
  local run_id="$1"
  local jobs_json
  jobs_json="$(list_run_jobs "${run_id}")"
  python3 -c '
import json
import sys

jobs = json.load(sys.stdin)
if not isinstance(jobs, list):
    raise SystemExit("workflow jobs response is malformed")

by_name = {
    job.get("name"): job
    for job in jobs
    if isinstance(job, dict) and isinstance(job.get("name"), str)
}
baseline = by_name.get("Baseline runner")
probe = by_name.get("Release environment probe")
if not isinstance(baseline, dict) or baseline.get("conclusion") != "success":
    raise SystemExit("baseline job must succeed before treating the proof as meaningful")
if not isinstance(probe, dict) or probe.get("conclusion") != "failure":
    raise SystemExit("release Environment probe job must fail for an unauthorized ref")
' <<<"${jobs_json}"
}

prove_ref_allowed() {
  local ref="$1"
  local suffix="$2"
  local title="Release Environment Negative Proof / ${nonce}-${suffix}"
  local baseline_run_ids="${temp_root}/baseline-${suffix}.json"
  local run_id conclusion

  snapshot_run_ids "${baseline_run_ids}"
  gh workflow run "${workflow_name}" --repo "${repository}" --ref "${ref}" -f "nonce=${nonce}-${suffix}"

  run_id="$(find_run_id "${title}" "${ref}" "${default_sha}" "${baseline_run_ids}")"
  conclusion="$(wait_for_completion "${run_id}")"
  if [[ "${conclusion}" != success ]]; then
    echo "Expected authorized ${suffix} run to succeed; got conclusion '${conclusion}'." >&2
    return 1
  fi
  assert_allowed_jobs "${run_id}"
}

prove_ref_denied() {
  local ref="$1"
  local suffix="$2"
  local title="Release Environment Negative Proof / ${nonce}-${suffix}"
  local baseline_run_ids="${temp_root}/baseline-${suffix}.json"
  local run_id conclusion

  snapshot_run_ids "${baseline_run_ids}"
  gh workflow run "${workflow_name}" --repo "${repository}" --ref "${ref}" -f "nonce=${nonce}-${suffix}"

  run_id="$(find_run_id "${title}" "${ref}" "${default_sha}" "${baseline_run_ids}")"
  conclusion="$(wait_for_completion "${run_id}")"
  if [[ "${conclusion}" != failure ]]; then
    echo "Expected unauthorized ${suffix} run to fail; got conclusion '${conclusion}'." >&2
    return 1
  fi
  assert_denied_jobs "${run_id}"
}

prove_ref_allowed "${default_branch}" default
echo "default branch admitted by release Environment policy"

prove_ref_denied "${branch_name}" branch
echo "unauthorized branch denied by release Environment policy"

prove_ref_denied "${tag_name}" tag
echo "unauthorized tag denied by release Environment policy"

final_repo_json="$(gh api "${api_headers[@]}" "repos/${repository}")"
final_commit_json="$(gh api "${api_headers[@]}" "repos/${repository}/commits/${encoded_default_branch}")"

python3 - "${repository_id}" "${repository_full_name}" "${default_branch}" "${default_sha}" "${repo_json}" "${final_repo_json}" "${final_commit_json}" <<'PY'
import json
import re
import sys

(
    expected_id_text,
    expected_full_name,
    expected_default_branch,
    expected_sha,
    initial_repository_json,
    final_repository_json,
    final_commit_json,
) = sys.argv[1:]

expected_id = int(expected_id_text)
initial_repository = json.loads(initial_repository_json)
final_repository = json.loads(final_repository_json)
final_commit = json.loads(final_commit_json)

if not isinstance(initial_repository, dict) or not isinstance(final_repository, dict):
    raise SystemExit("repository identity snapshots must be JSON objects")

checks = (
    (
        initial_repository.get("id") == expected_id,
        "initial repository id does not match captured identity",
    ),
    (
        initial_repository.get("full_name") == expected_full_name,
        "initial repository full_name does not match captured identity",
    ),
    (
        initial_repository.get("default_branch") == expected_default_branch,
        "initial repository default_branch does not match captured identity",
    ),
    (
        final_repository.get("id") == expected_id,
        "repository id changed during Environment proof",
    ),
    (
        final_repository.get("full_name") == expected_full_name,
        "repository full_name changed during Environment proof",
    ),
    (
        final_repository.get("default_branch") == expected_default_branch,
        "repository default_branch changed during Environment proof",
    ),
)
for ok, message in checks:
    if not ok:
        raise SystemExit(message)

final_sha = final_commit.get("sha")
if not isinstance(final_sha, str) or re.fullmatch(r"[0-9a-f]{40}", final_sha) is None:
    raise SystemExit("final default branch response has no canonical commit SHA")
if final_sha != expected_sha:
    raise SystemExit("default branch head changed during Environment proof")
PY

if ! cleanup_refs_strict; then
  echo "Release Environment proof checks passed, but temporary ref cleanup failed." >&2
  exit 4
fi

rm -rf "${temp_root}"
trap - EXIT

echo "release Environment negative runtime proof passed for ${repository}"
