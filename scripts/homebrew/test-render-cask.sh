#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEMP_ROOT}"' EXIT

template="${TEMP_ROOT}/template.rb"
output="${TEMP_ROOT}/rendered.rb"
sentinel="${TEMP_ROOT}/interpolated"

cat >"${template}" <<'RUBY'
puts "{{DESCRIPTION}}"
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
printf 'Homebrew Cask renderer interpolation test passed\n'
