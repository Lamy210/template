#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${ROOT}/scripts/visual/collect-metadata.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[[ -f "${SCRIPT}" ]] || fail "collect-metadata.sh must exist"

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
mkdir -p "${tmp}/bin"

cat >"${tmp}/bin/xcodebuild" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'Xcode 26.6\nBuild version 17G86\n'
STUB
chmod +x "${tmp}/bin/xcodebuild"

cat >"${tmp}/bin/sw_vers" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-buildVersion" ]]; then
  printf '25G90\n'
  exit 0
fi
exit 2
STUB
chmod +x "${tmp}/bin/sw_vers"

output="${tmp}/profile.json"
PATH="${tmp}/bin:${PATH}" ImageVersion="macos-26-arm64-20260901" \
  bash "${SCRIPT}" \
  --output "${output}" \
  --profile-id "macos-26-arm64-xcode-26.6" \
  --current-sha "0123456789abcdef0123456789abcdef01234567" \
  --runner-family "macos-26" \
  --architecture "ARM64" \
  --xcode-policy "Xcode 26.6" \
  --locale "en_US.UTF-8" \
  --language "en" \
  --timezone "UTC" \
  --appearance "controlled-by-test" \
  --display-scale "2x" \
  --capture-geometry "window-or-element" \
  --fixture-version "fixture-v1" \
  --capture-contract-version 1 \
  --comparator-schema-version 1

python3 - "${output}" <<'PY'
import hashlib
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

assert payload["schemaVersion"] == 2
assert payload["profile"] == "macos-26-arm64-xcode-26.6"
assert payload["currentSHA"] == "0123456789abcdef0123456789abcdef01234567"
assert payload["controlled"]["runnerFamily"] == "macos-26"
assert payload["controlled"]["architecture"] == "ARM64"
assert payload["controlled"]["xcodePolicy"] == "Xcode 26.6"
assert payload["observed"]["macOSBuild"] == "25G90"
assert payload["observed"]["runnerImageVersion"] == "macos-26-arm64-20260901"
assert payload["observed"]["xcodeBuild"] == "Xcode 26.6 | Build version 17G86"

canonical = json.dumps(
    payload["controlled"],
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
expected = "sha256:" + hashlib.sha256(canonical).hexdigest()
assert payload["profileFingerprint"] == expected
PY

if PATH="${tmp}/bin:${PATH}" bash "${SCRIPT}" \
  --output "${tmp}/invalid.json" \
  --profile-id "" \
  --current-sha "abc" \
  --runner-family "macos-26" \
  --architecture "ARM64" \
  --xcode-policy "Xcode 26.6" \
  --locale "en_US.UTF-8" \
  --language "en" \
  --timezone "UTC" \
  --appearance "controlled-by-test" \
  --display-scale "2x" \
  --capture-geometry "window-or-element" \
  --fixture-version "fixture-v1" \
  --capture-contract-version 1 \
  --comparator-schema-version 1; then
  fail "empty profile id must be rejected"
fi

if PATH="${tmp}/bin:${PATH}" bash "${SCRIPT}" \
  --output "${tmp}/invalid-version.json" \
  --profile-id "profile" \
  --current-sha "abc" \
  --runner-family "macos-26" \
  --architecture "ARM64" \
  --xcode-policy "Xcode 26.6" \
  --locale "en_US.UTF-8" \
  --language "en" \
  --timezone "UTC" \
  --appearance "controlled-by-test" \
  --display-scale "2x" \
  --capture-geometry "window-or-element" \
  --fixture-version "fixture-v1" \
  --capture-contract-version 0 \
  --comparator-schema-version 1; then
  fail "non-positive capture contract version must be rejected"
fi

echo "collect-metadata tests passed"
