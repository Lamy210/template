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

symlink_target="${TEMP_ROOT}/symlink-target.rb"
printf 'do-not-overwrite\n' >"${symlink_target}"
symlink_output="${TEMP_ROOT}/symlink-output.rb"
ln -s "${symlink_target}" "${symlink_output}"

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
  OUTPUT_CASK="${symlink_output}" \
  bash "${REPO_ROOT}/scripts/homebrew/render-cask.sh" \
  >"${TEMP_ROOT}/symlink.stdout" \
  2>"${TEMP_ROOT}/symlink.stderr"
status=$?
set -e
if [[ "${status}" -eq 0 ]]; then
  echo 'Symlinked Cask output was accepted.' >&2
  exit 1
fi
grep -Fx 'do-not-overwrite' "${symlink_target}" >/dev/null

real_casks="${TEMP_ROOT}/real-casks"
linked_casks="${TEMP_ROOT}/linked-casks"
mkdir -p "${real_casks}"
ln -s "${real_casks}" "${linked_casks}"

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
  OUTPUT_CASK="${linked_casks}/example-app.rb" \
  bash "${REPO_ROOT}/scripts/homebrew/render-cask.sh" \
  >"${TEMP_ROOT}/parent-symlink.stdout" \
  2>"${TEMP_ROOT}/parent-symlink.stderr"
status=$?
set -e
if [[ "${status}" -eq 0 ]]; then
  echo 'Cask output below a symlinked parent was accepted.' >&2
  exit 1
fi
if [[ -e "${real_casks}/example-app.rb" ]]; then
  echo 'Renderer wrote through a symlinked output parent.' >&2
  exit 1
fi

printf 'Homebrew Cask renderer interpolation and output-confinement test passed\n'
