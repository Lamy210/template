#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
doctor="${repo_root}/scripts/ci/audit-live-immutable-releases.sh"

temp_root="$(mktemp -d)"
cleanup() {
  rm -rf "${temp_root}"
}
trap cleanup EXIT

fake_bin="${temp_root}/bin"
mkdir -p "${fake_bin}"

cat >"${fake_bin}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail

: "${GH_FAKE_SCENARIO:?}"
: "${GH_FAKE_STATE:?}"
: "${GH_FAKE_LOG:?}"

printf '%s\n' "$*" >>"${GH_FAKE_LOG}"
args="$*"

if [[ "${args}" == *"repos/Example/Repo/immutable-releases"* ]]; then
  : >"${GH_FAKE_STATE}"
  case "${GH_FAKE_SCENARIO}" in
    enabled | repository-drift)
      printf '%s\n' '{"enabled":true,"enforced_by_owner":false}'
      exit 0
      ;;
    owner-enforced)
      printf '%s\n' '{"enabled":true,"enforced_by_owner":true}'
      exit 0
      ;;
    malformed)
      printf '%s\n' '{"enabled":false,"enforced_by_owner":false}'
      exit 0
      ;;
    unavailable)
      echo "HTTP 404: Not Found" >&2
      exit 1
      ;;
    *)
      exit 98
      ;;
  esac
fi

if [[ "${args}" == *"repos/Example/Repo"* ]]; then
  repository_id=123
  if [[ "${GH_FAKE_SCENARIO}" == "repository-drift" && -f "${GH_FAKE_STATE}" ]]; then
    repository_id=999
  fi
  printf '{"id":%s,"full_name":"Example/Repo"}\n' "${repository_id}"
  exit 0
fi

echo "Unexpected fake gh invocation: $*" >&2
exit 97
FAKE_GH
chmod 0755 "${fake_bin}/gh"

run_doctor() {
  local scenario="$1"
  GH_FAKE_SCENARIO="${scenario}" \
    GH_FAKE_STATE="${temp_root}/state" \
    GH_FAKE_LOG="${temp_root}/gh.log" \
    PATH="${fake_bin}:${PATH}" \
    bash "${doctor}" Example/Repo
}

rm -f "${temp_root}/state"
: >"${temp_root}/gh.log"
output="$(run_doctor enabled)"
grep -F "native immutable releases enabled for Example/Repo" <<<"${output}" >/dev/null
grep -F "enforced_by_owner=false" <<<"${output}" >/dev/null
[[ "$(grep -Fc "repos/Example/Repo" "${temp_root}/gh.log")" -eq 3 ]]
if grep -E -- "--method (PUT|POST|PATCH|DELETE)" "${temp_root}/gh.log" >/dev/null; then
  echo "Immutable release doctor unexpectedly attempted a mutation." >&2
  exit 1
fi

rm -f "${temp_root}/state"
: >"${temp_root}/gh.log"
output="$(run_doctor owner-enforced)"
grep -F "enforced_by_owner=true" <<<"${output}" >/dev/null

rm -f "${temp_root}/state"
: >"${temp_root}/gh.log"
if run_doctor unavailable >"${temp_root}/unavailable.out" 2>"${temp_root}/unavailable.err"; then
  echo "Immutable release doctor accepted unavailable/disabled endpoint." >&2
  exit 1
fi
grep -F "Unable to prove native immutable releases are enabled" "${temp_root}/unavailable.err" >/dev/null
grep -F "Administration(read)" "${temp_root}/unavailable.err" >/dev/null

rm -f "${temp_root}/state"
: >"${temp_root}/gh.log"
if run_doctor malformed >"${temp_root}/malformed.out" 2>"${temp_root}/malformed.err"; then
  echo "Immutable release doctor accepted disabled setting payload." >&2
  exit 1
fi
grep -F "must be enabled" "${temp_root}/malformed.err" >/dev/null

rm -f "${temp_root}/state"
: >"${temp_root}/gh.log"
if run_doctor repository-drift >"${temp_root}/drift.out" 2>"${temp_root}/drift.err"; then
  echo "Immutable release doctor accepted repository identity drift." >&2
  exit 1
fi
grep -F "Repository identity changed" "${temp_root}/drift.err" >/dev/null

rm -f "${temp_root}/state"
: >"${temp_root}/gh.log"
if GH_FAKE_SCENARIO=enabled \
  GH_FAKE_STATE="${temp_root}/state" \
  GH_FAKE_LOG="${temp_root}/gh.log" \
  PATH="${fake_bin}:${PATH}" \
  bash "${doctor}" ../escape >"${temp_root}/preflight.out" 2>"${temp_root}/preflight.err"; then
  echo "Immutable release doctor accepted malformed repository input." >&2
  exit 1
fi
[[ ! -s "${temp_root}/gh.log" ]]
grep -F "invalid owner or repository component" "${temp_root}/preflight.err" >/dev/null

echo "native immutable release audit regression passed"
