#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

template="${TEMP_ROOT}/template.rb"
output="${TEMP_ROOT}/rendered.rb"
sentinel="${TEMP_ROOT}/interpolated"

cat >"${template}" <<'RUBY'
version = "1.2.3"
puts "{{DESCRIPTION}}"
puts "{{DMG_BASENAME}}"
RUBY

dangerous='#{File.write(ENV.fetch(%q{INTERPOLATION_SENTINEL}), %q{executed})}'

CASK_TEMPLATE="${template}" \
  CASK_TOKEN='example-app' \
  VERSION='1.2.3' \
  SHA256='0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' \
  GITHUB_OWNER='example' \
  GITHUB_REPO='example-app' \
  DMG_BASENAME='ExampleApp-v#{version}.dmg' \
  APP_NAME='ExampleApp' \
  DESCRIPTION="${dangerous}" \
  HOMEPAGE='https://example.com' \
  BUNDLE_ID='com.example.ExampleApp' \
  CASK_OUTPUT_ROOT="${TEMP_ROOT}" \
  OUTPUT_CASK="${output}" \
  bash "${REPO_ROOT}/scripts/homebrew/render-cask.sh"

INTERPOLATION_SENTINEL="${sentinel}" ruby "${output}" >"${TEMP_ROOT}/stdout"

if [[ -e "${sentinel}" ]]; then
  echo 'Ruby interpolation from a rendered Cask string was executed.' >&2
  exit 1
fi

grep -F "${dangerous}" "${TEMP_ROOT}/stdout" >/dev/null
grep -F 'ExampleApp-v1.2.3.dmg' "${TEMP_ROOT}/stdout" >/dev/null

malicious_dmg='ExampleApp-v#{File.write(ENV.fetch(%q{INTERPOLATION_SENTINEL}), %q{executed})}.dmg'
set +e
CASK_TEMPLATE="${template}" \
  CASK_TOKEN='example-app' \
  VERSION='1.2.3' \
  SHA256='0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' \
  GITHUB_OWNER='example' \
  GITHUB_REPO='example-app' \
  DMG_BASENAME="${malicious_dmg}" \
  APP_NAME='ExampleApp' \
  DESCRIPTION='safe description' \
  HOMEPAGE='https://example.com' \
  BUNDLE_ID='com.example.ExampleApp' \
  CASK_OUTPUT_ROOT="${TEMP_ROOT}" \
  OUTPUT_CASK="${TEMP_ROOT}/malicious.rb" \
  bash "${REPO_ROOT}/scripts/homebrew/render-cask.sh" \
  >"${TEMP_ROOT}/malicious.stdout" \
  2>"${TEMP_ROOT}/malicious.stderr"
status=$?
set -e
if [[ "${status}" -eq 0 ]]; then
  echo 'Unsafe DMG basename interpolation was accepted.' >&2
  exit 1
fi

mkdir "${TEMP_ROOT}/outside-casks"
ln -s "${TEMP_ROOT}/outside-casks" "${TEMP_ROOT}/linked-casks"
set +e
CASK_TEMPLATE="${template}" \
  CASK_TOKEN='example-app' \
  VERSION='1.2.3' \
  SHA256='0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' \
  GITHUB_OWNER='example' \
  GITHUB_REPO='example-app' \
  DMG_BASENAME='ExampleApp-v#{version}.dmg' \
  APP_NAME='ExampleApp' \
  DESCRIPTION='safe description' \
  HOMEPAGE='https://example.com' \
  BUNDLE_ID='com.example.ExampleApp' \
  CASK_OUTPUT_ROOT="${TEMP_ROOT}" \
  OUTPUT_CASK="${TEMP_ROOT}/linked-casks/example-app.rb" \
  bash "${REPO_ROOT}/scripts/homebrew/render-cask.sh" \
  >"${TEMP_ROOT}/symlink.stdout" \
  2>"${TEMP_ROOT}/symlink.stderr"
status=$?
set -e
if [[ "${status}" -eq 0 ]]; then
  echo 'Symlinked Cask output parent was accepted.' >&2
  exit 1
fi
if [[ -e "${TEMP_ROOT}/outside-casks/example-app.rb" ]]; then
  echo 'Renderer wrote through a symlinked Cask output parent.' >&2
  exit 1
fi

real_python3="$(command -v python3)"
race_bin="${TEMP_ROOT}/race-bin"
race_counter="${TEMP_ROOT}/python3-count"
race_output="${TEMP_ROOT}/race.rb"
race_victim="${TEMP_ROOT}/victim.rb"
mkdir "${race_bin}"
printf 'do-not-touch\n' >"${race_victim}"
cat >"${race_bin}/python3" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
count=0
if [[ -f "${PYTHON3_RACE_COUNTER}" ]]; then
  read -r count <"${PYTHON3_RACE_COUNTER}"
fi
count=$((count + 1))
printf '%s\n' "${count}" >"${PYTHON3_RACE_COUNTER}"
if [[ "${count}" -eq 3 ]]; then
  rm -f "${PYTHON3_RACE_OUTPUT}"
  ln -s "${PYTHON3_RACE_VICTIM}" "${PYTHON3_RACE_OUTPUT}"
fi
exec "${REAL_PYTHON3}" "$@"
WRAPPER
chmod +x "${race_bin}/python3"

set +e
PATH="${race_bin}:${PATH}" \
  REAL_PYTHON3="${real_python3}" \
  PYTHON3_RACE_COUNTER="${race_counter}" \
  PYTHON3_RACE_OUTPUT="${race_output}" \
  PYTHON3_RACE_VICTIM="${race_victim}" \
  CASK_TEMPLATE="${template}" \
  CASK_TOKEN='example-app' \
  VERSION='1.2.3' \
  SHA256='0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' \
  GITHUB_OWNER='example' \
  GITHUB_REPO='example-app' \
  DMG_BASENAME='ExampleApp-v#{version}.dmg' \
  APP_NAME='ExampleApp' \
  DESCRIPTION='safe description' \
  HOMEPAGE='https://example.com' \
  BUNDLE_ID='com.example.ExampleApp' \
  CASK_OUTPUT_ROOT="${TEMP_ROOT}" \
  OUTPUT_CASK="${race_output}" \
  bash "${REPO_ROOT}/scripts/homebrew/render-cask.sh" \
  >"${TEMP_ROOT}/race.stdout" \
  2>"${TEMP_ROOT}/race.stderr"
status=$?
set -e
if [[ "${status}" -eq 0 ]]; then
  echo 'Renderer accepted an output symlink introduced after path validation.' >&2
  exit 1
fi
if [[ "$(cat "${race_victim}")" != 'do-not-touch' ]]; then
  echo 'Renderer overwrote a symlink target introduced after path validation.' >&2
  exit 1
fi

printf 'Homebrew Cask renderer interpolation test passed\n'
