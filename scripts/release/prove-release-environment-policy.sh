#!/usr/bin/env bash
set -euo pipefail

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
if [[ ! "${workflow_name}" =~ ^[A-Za-z0-9_.-]+\.ya?ml$ ]]; then
  echo "--workflow must be a workflow filename such as release-environment-proof.yml." >&2
  exit 2
fi

for command_name in gh python3; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

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

commit_json="$(gh api "${api_headers[@]}" "repos/${repository}/commits/${default_branch}")"
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

gh api "${api_headers[@]}" "repos/${repository}/contents/.github/workflows/${workflow_name}?ref=${default_branch}" >/dev/null

branch_name="environment-proof/${nonce}"
tag_name="environment-proof-${nonce}"
branch_created=false
tag_created=false

cleanup() {
  if [[ "${branch_created}" == true ]]; then
    gh api "${api_headers[@]}" --method DELETE "repos/${repository}/git/refs/heads/${branch_name}" >/dev/null 2>&1 || true
  fi
  if [[ "${tag_created}" == true ]]; then
    gh api "${api_headers[@]}" --method DELETE "repos/${repository}/git/refs/tags/${tag_name}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

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

find_run_id() {
  local title="$1"
  local attempt list_json run_id
  for ((attempt = 1; attempt <= poll_attempts; attempt++)); do
    list_json="$(
      gh run list --repo "${repository}" --workflow "${workflow_name}" --event workflow_dispatch --limit 100 --json databaseId,displayTitle
    )"
    run_id="$(
      python3 -c '
import json
import sys

title = sys.argv[1]
runs = json.load(sys.stdin)
matches = [
    item.get("databaseId")
    for item in runs
    if isinstance(item, dict) and item.get("displayTitle") == title
]
matches = [value for value in matches if type(value) is int and value > 0]
if len(matches) == 1:
    print(matches[0])
' "${title}" <<<"${list_json}"
    )"
    if [[ "${run_id}" =~ ^[1-9][0-9]*$ ]]; then
      printf '%s\n' "${run_id}"
      return 0
    fi
    sleep "${poll_seconds}"
  done
  echo "Unable to locate dispatched workflow run: ${title}" >&2
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

assert_allowed_jobs() {
  local run_id="$1"
  local jobs_json
  jobs_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${run_id}/jobs?per_page=100")"
  python3 -c '
import json
import sys

document = json.load(sys.stdin)
jobs = document.get("jobs")
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
  jobs_json="$(gh api "${api_headers[@]}" "repos/${repository}/actions/runs/${run_id}/jobs?per_page=100")"
  python3 -c '
import json
import sys

document = json.load(sys.stdin)
jobs = document.get("jobs")
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
  local run_id conclusion

  gh workflow run "${workflow_name}" --repo "${repository}" --ref "${ref}" -f "nonce=${nonce}-${suffix}"

  run_id="$(find_run_id "${title}")"
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
  local run_id conclusion

  gh workflow run "${workflow_name}" --repo "${repository}" --ref "${ref}" -f "nonce=${nonce}-${suffix}"

  run_id="$(find_run_id "${title}")"
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

echo "release Environment negative runtime proof passed for ${repository}"
