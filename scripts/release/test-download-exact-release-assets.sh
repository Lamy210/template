#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
downloader="${repo_root}/scripts/release/download-exact-release-assets.sh"

temp_root="$(mktemp -d)"
cleanup() {
  rm -rf "${temp_root}"
}
trap cleanup EXIT

fake_bin="${temp_root}/bin"
mkdir -p "${fake_bin}"

printf 'dmg-payload\n' >"${temp_root}/dmg"
printf 'checksum-payload\n' >"${temp_root}/checksum"
printf 'provenance-payload\n' >"${temp_root}/provenance"

cat >"${fake_bin}/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >>"${GH_FAKE_LOG:?}"

emit_release() {
  python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import os

repository = "Example/MyApp"
tag = "v1.2.3"
scenario = os.environ["GH_FAKE_SCENARIO"]
payloads = [
    (101, "MyApp-v1.2.3.dmg", Path(os.environ["GH_FAKE_DMG"])),
    (102, "MyApp-v1.2.3.dmg.sha256", Path(os.environ["GH_FAKE_CHECKSUM"])),
    (103, "release-provenance.json", Path(os.environ["GH_FAKE_PROVENANCE"])),
]
assets = []
for asset_id, name, path in payloads:
    payload = path.read_bytes()
    if scenario == "release-drift" and os.environ.get("GH_FAKE_AFTER_DOWNLOAD") == "1" and name == "release-provenance.json":
        asset_id = 104
    assets.append(
        {
            "id": asset_id,
            "name": name,
            "state": "uploaded",
            "size": len(payload),
            "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "url": f"https://api.github.com/repos/{repository}/releases/assets/{asset_id}",
            "browser_download_url": (
                f"https://github.com/{repository}/releases/download/{tag}/{name}"
            ),
        }
    )

print(
    json.dumps(
        {
            "id": 700,
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "immutable": False,
            "url": f"https://api.github.com/repos/{repository}/releases/700",
            "assets": assets,
        },
        separators=(",", ":"),
    )
)
PY
}

args="$*"
if [[ "${args}" == *"repos/Example/MyApp/releases/tags/v1.2.3"* ]]; then
  emit_release
  exit 0
fi
if [[ "${args}" == *"repos/Example/MyApp/releases/700"* ]]; then
  GH_FAKE_AFTER_DOWNLOAD=1 emit_release
  exit 0
fi
if [[ "${args}" == *"repos/Example/MyApp/releases/assets/101"* ]]; then
  if [[ "${GH_FAKE_SCENARIO}" == "corrupt-dmg" ]]; then
    printf 'corrupt-dmg\n'
  else
    cat "${GH_FAKE_DMG}"
  fi
  exit 0
fi
if [[ "${args}" == *"repos/Example/MyApp/releases/assets/102"* ]]; then
  cat "${GH_FAKE_CHECKSUM}"
  exit 0
fi
if [[ "${args}" == *"repos/Example/MyApp/releases/assets/103"* ]]; then
  cat "${GH_FAKE_PROVENANCE}"
  exit 0
fi

echo "Unexpected fake gh invocation: $*" >&2
exit 90
FAKE_GH
chmod 0755 "${fake_bin}/gh"

run_downloader() {
  local scenario="$1"
  local output_dir="$2"
  GH_FAKE_SCENARIO="${scenario}" \
    GH_FAKE_LOG="${temp_root}/gh.log" \
    GH_FAKE_DMG="${temp_root}/dmg" \
    GH_FAKE_CHECKSUM="${temp_root}/checksum" \
    GH_FAKE_PROVENANCE="${temp_root}/provenance" \
    PATH="${fake_bin}:${PATH}" \
    bash "${downloader}" \
      --repository Example/MyApp \
      --tag v1.2.3 \
      --output-dir "${output_dir}" \
      --asset MyApp-v1.2.3.dmg \
      --asset MyApp-v1.2.3.dmg.sha256 \
      --asset release-provenance.json
}

: >"${temp_root}/gh.log"
success_output="${temp_root}/success"
run_downloader success "${success_output}"

cmp -s "${success_output}/MyApp-v1.2.3.dmg" "${temp_root}/dmg"
cmp -s "${success_output}/MyApp-v1.2.3.dmg.sha256" "${temp_root}/checksum"
cmp -s "${success_output}/release-provenance.json" "${temp_root}/provenance"
[[ -f "${success_output}/release-download-manifest.json" ]]
grep -F "releases/assets/101" "${temp_root}/gh.log" >/dev/null
grep -F "releases/assets/102" "${temp_root}/gh.log" >/dev/null
grep -F "releases/assets/103" "${temp_root}/gh.log" >/dev/null
grep -F "releases/700" "${temp_root}/gh.log" >/dev/null
if grep -F "release download" "${temp_root}/gh.log" >/dev/null; then
  echo "Exact release downloader unexpectedly used gh release download." >&2
  exit 1
fi

: >"${temp_root}/gh.log"
corrupt_output="${temp_root}/corrupt"
if run_downloader corrupt-dmg "${corrupt_output}" >"${temp_root}/corrupt.out" 2>"${temp_root}/corrupt.err"; then
  echo "Exact release downloader accepted corrupted asset bytes." >&2
  exit 1
fi
grep -F "digest mismatch" "${temp_root}/corrupt.err" >/dev/null

: >"${temp_root}/gh.log"
drift_output="${temp_root}/drift"
if run_downloader release-drift "${drift_output}" >"${temp_root}/drift.out" 2>"${temp_root}/drift.err"; then
  echo "Exact release downloader accepted release identity drift." >&2
  exit 1
fi
grep -F "Release or asset identity changed" "${temp_root}/drift.err" >/dev/null

echo "exact release asset download regression passed"
