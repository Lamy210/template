#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERIFIER="${REPO_ROOT}/scripts/release/verify-release-source.sh"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT
REAL_GIT="$(command -v git)"

origin="${TEMP_ROOT}/origin.git"
work="${TEMP_ROOT}/work"
git init --bare "${origin}" >/dev/null
git init -b main "${work}" >/dev/null
(
  cd "${work}"
  git config user.name Test
  git config user.email test@example.com
  printf 'one\n' >app.txt
  git add app.txt
  git commit -m one >/dev/null
  first="$(git rev-parse HEAD)"
  git tag v1.0.0
  git tag -a v1.0.1 -m annotated

  printf 'two\n' >>app.txt
  git commit -am two >/dev/null
  second="$(git rev-parse HEAD)"

  git checkout --orphan unrelated >/dev/null 2>&1
  git rm -rf . >/dev/null 2>&1 || true
  printf 'other\n' >other.txt
  git add other.txt
  git commit -m unrelated >/dev/null
  unrelated="$(git rev-parse HEAD)"
  git tag v9.9.9
  git checkout main >/dev/null 2>&1

  git remote add origin "${origin}"
  git push origin main --tags >/dev/null
  printf '%s\n%s\n%s\n' "${first}" "${second}" "${unrelated}" >"${TEMP_ROOT}/shas"
)

mapfile -t shas <"${TEMP_ROOT}/shas"
first="${shas[0]}"
second="${shas[1]}"
unrelated="${shas[2]}"

clone="${TEMP_ROOT}/clone"
git clone --no-tags "${origin}" "${clone}" >/dev/null 2>&1

STUB_BIN="${TEMP_ROOT}/bin"
mkdir -p "${STUB_BIN}"

cat >"${STUB_BIN}/git" <<STUB
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == fetch ]]; then
  echo 'verify-release-source must not depend on credential-persisted git fetch' >&2
  exit 91
fi
exec "${REAL_GIT}" "\$@"
STUB
chmod +x "${STUB_BIN}/git"

cat >"${STUB_BIN}/gh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${TEST_FIRST_SHA:?TEST_FIRST_SHA is required}"
: "${TEST_UNRELATED_SHA:?TEST_UNRELATED_SHA is required}"
args="$*"
annotated_sha='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'

case "${args}" in
  *"/git/ref/tags/v1.0.0"*)
    printf '{"ref":"refs/tags/v1.0.0","object":{"type":"commit","sha":"%s"}}' "${TEST_FIRST_SHA}"
    ;;
  *"/git/ref/tags/v1.0.1"*)
    printf '{"ref":"refs/tags/v1.0.1","object":{"type":"tag","sha":"%s"}}' "${annotated_sha}"
    ;;
  *"/git/tags/${annotated_sha}"*)
    printf '{"sha":"%s","object":{"type":"commit","sha":"%s"}}' "${annotated_sha}" "${TEST_FIRST_SHA}"
    ;;
  *"/git/ref/tags/v9.9.9"*)
    printf '{"ref":"refs/tags/v9.9.9","object":{"type":"commit","sha":"%s"}}' "${TEST_UNRELATED_SHA}"
    ;;
  *)
    printf 'unexpected gh invocation: %s\n' "${args}" >&2
    exit 2
    ;;
esac
STUB
chmod +x "${STUB_BIN}/gh"

run_verify() {
  local tag="$1"
  local source_sha="$2"
  local publisher_sha="$3"
  (
    cd "${clone}"
    PATH="${STUB_BIN}:${PATH}" \
      GH_TOKEN="test-token" \
      GITHUB_REPOSITORY="Lamy210/template" \
      TEST_FIRST_SHA="${first}" \
      TEST_UNRELATED_SHA="${unrelated}" \
      SOURCE_TAG="${tag}" \
      SOURCE_SHA="${source_sha}" \
      PUBLISHER_SHA="${publisher_sha}" \
      bash "${VERIFIER}"
  )
}

resolved="$(run_verify v1.0.0 "${first}" "${second}")"
[[ "${resolved}" == "${first}" ]]

annotated_resolved="$(run_verify v1.0.1 "${first}" "${second}")"
[[ "${annotated_resolved}" == "${first}" ]]

if run_verify v1.0.0 "${second}" "${second}" >/dev/null 2>&1; then
  echo 'mismatched tag/source SHA was accepted' >&2
  exit 1
fi

if run_verify v9.9.9 "${unrelated}" "${second}" >/dev/null 2>&1; then
  echo 'source outside trusted publisher history was accepted' >&2
  exit 1
fi

if run_verify 'bad/tag' "${first}" "${second}" >/dev/null 2>&1; then
  echo 'unsafe tag name was accepted' >&2
  exit 1
fi

if run_verify v1.0.0 INVALID "${second}" >/dev/null 2>&1; then
  echo 'invalid source SHA was accepted' >&2
  exit 1
fi

printf 'release source verification tests passed\n'
