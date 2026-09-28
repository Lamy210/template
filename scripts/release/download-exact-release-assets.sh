#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  download-exact-release-assets.sh \
    --repository owner/repo \
    --repository-id 123456 \
    --tag v1.2.3 \
    --output-dir release-assets \
    --asset App-v1.2.3.dmg \
    --asset App-v1.2.3.dmg.sha256 \
    --asset release-provenance.json
EOF
}

repository=""
repository_id=""
tag=""
output_dir=""
assets=()

while (($# > 0)); do
  case "$1" in
    --repository)
      [[ $# -ge 2 ]] || {
        usage
        exit 2
      }
      repository="$2"
      shift 2
      ;;
    --repository-id)
      [[ $# -ge 2 ]] || {
        usage
        exit 2
      }
      repository_id="$2"
      shift 2
      ;;
    --tag)
      [[ $# -ge 2 ]] || {
        usage
        exit 2
      }
      tag="$2"
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || {
        usage
        exit 2
      }
      output_dir="$2"
      shift 2
      ;;
    --asset)
      [[ $# -ge 2 ]] || {
        usage
        exit 2
      }
      assets+=("$2")
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "${repository}" || -z "${repository_id}" || -z "${tag}" || -z "${output_dir}" || "${#assets[@]}" -eq 0 ]]; then
  usage
  exit 2
fi

for command_name in gh python3 cmp mv mktemp rm cp; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "${command_name} is required." >&2
    exit 2
  }
done

if [[ -e "${output_dir}" || -L "${output_dir}" ]]; then
  echo "Output directory must not already exist: ${output_dir}" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
resolver="${repo_root}/scripts/release/resolve-release-download.py"
[[ -f "${resolver}" ]] || {
  echo "Release download resolver is unavailable: ${resolver}" >&2
  exit 2
}

temp_root="$(mktemp -d)"
cleanup() {
  rm -rf "${temp_root}"
}
trap cleanup EXIT

api_headers=(
  -H 'Accept: application/vnd.github+json'
  -H 'X-GitHub-Api-Version: 2026-03-10'
)

repository_identity() {
  local response
  if ! response="$(gh api "${api_headers[@]}" --method GET "repos/${repository}")"; then
    echo "Failed to resolve release repository identity." >&2
    return 1
  fi

  python3 - "${repository}" "${repository_id}" "${response}" <<'PY'
import json
import re
import sys

expected_name, expected_id_text, response = sys.argv[1:]
if re.fullmatch(r"[1-9][0-9]*", expected_id_text) is None:
    raise SystemExit("expected repository id must be a positive integer")
expected_id = int(expected_id_text)

try:
    document = json.loads(response)
except json.JSONDecodeError as error:
    raise SystemExit(f"repository identity response is invalid JSON: {error}")
if not isinstance(document, dict):
    raise SystemExit("repository identity response must be an object")

repository_id = document.get("id")
full_name = document.get("full_name")
if type(repository_id) is not int or repository_id <= 0:
    raise SystemExit("repository identity response has invalid id")
if (
    not isinstance(full_name, str)
    or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) is None
):
    raise SystemExit("repository identity response has invalid full_name")
if repository_id != expected_id:
    raise SystemExit(
        f"repository id mismatch: expected {expected_id}, got {repository_id}"
    )
if full_name.casefold() != expected_name.casefold():
    raise SystemExit(
        f"repository full_name mismatch: expected {expected_name!r}, got {full_name!r}"
    )

print(repository_id)
print(full_name.casefold())
PY
}

if ! initial_repository_identity="$(repository_identity)"; then
  echo "Unable to bind release repository identity before downloads." >&2
  exit 1
fi

metadata_before="${temp_root}/release-before.json"
manifest_before="${temp_root}/manifest-before.json"
plan="${temp_root}/download-plan.tsv"

if ! gh api "${api_headers[@]}" --method GET \
  "repos/${repository}/releases/tags/${tag}" >"${metadata_before}"; then
  echo "Failed to resolve release by tag: ${repository}@${tag}" >&2
  exit 1
fi

resolver_args=(
  --metadata "${metadata_before}"
  --repository "${repository}"
  --tag "${tag}"
  --output "${manifest_before}"
)
for asset_name in "${assets[@]}"; do
  resolver_args+=(--asset "${asset_name}")
done
python3 "${resolver}" "${resolver_args[@]}"

release_id="$(
  python3 - "${manifest_before}" <<'PY'
import json
from pathlib import Path
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
release_id = document.get("releaseId")
if type(release_id) is not int or release_id <= 0:
    raise SystemExit("release download manifest has invalid releaseId")
print(release_id)
PY
)"

python3 - "${manifest_before}" <<'PY' >"${plan}"
import json
from pathlib import Path
import re
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assets = document.get("assets")
if not isinstance(assets, list) or not assets:
    raise SystemExit("release download manifest has no assets")
for asset in assets:
    if not isinstance(asset, dict):
        raise SystemExit("release download manifest asset must be an object")
    asset_id = asset.get("id")
    name = asset.get("name")
    digest = asset.get("digest")
    size = asset.get("size")
    if type(asset_id) is not int or asset_id <= 0:
        raise SystemExit("release download manifest asset has invalid id")
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name) is None:
        raise SystemExit("release download manifest asset has unsafe name")
    if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise SystemExit("release download manifest asset has invalid digest")
    if type(size) is not int or size <= 0:
        raise SystemExit("release download manifest asset has invalid size")
    print(f"{asset_id}\t{name}\t{digest}\t{size}")
PY

mkdir "${output_dir}"

while IFS=    echo "Release download plan contains an empty field." >&2
    exit 1
  }

  partial="${output_dir}/.${asset_name}.partial"
  destination="${output_dir}/${asset_name}"
  if ! gh api \
    -H 'Accept: application/octet-stream' \
    -H 'X-GitHub-Api-Version: 2026-03-10' \
    --method GET \
    "repos/${repository}/releases/assets/${asset_id}" >"${partial}"; then
    echo "Failed to download exact release asset id ${asset_id} (${asset_name})." >&2
    exit 1
  fi

  actual_digest="$(
    python3 - "${partial}" <<'PY'
from pathlib import Path
import hashlib
import sys

path = Path(sys.argv[1])
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(f"sha256:{digest}")
PY
  )"
  if [[ "${actual_digest}" != "${expected_digest}" ]]; then
    echo "Downloaded release asset digest mismatch for ${asset_name}." >&2
    exit 1
  fi
  actual_size="$(
    python3 - "${partial}" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).stat().st_size)
PY
  )"
  if [[ "${actual_size}" != "${expected_size}" ]]; then
    echo "Downloaded release asset size mismatch for ${asset_name}." >&2
    exit 1
  fi
  mv "${partial}" "${destination}"
done <"${plan}"

metadata_after="${temp_root}/release-after.json"
manifest_after="${temp_root}/manifest-after.json"
if ! gh api "${api_headers[@]}" --method GET \
  "repos/${repository}/releases/${release_id}" >"${metadata_after}"; then
  echo "Failed to re-resolve release id ${release_id} after downloads." >&2
  exit 1
fi

resolver_args=(
  --metadata "${metadata_after}"
  --repository "${repository}"
  --tag "${tag}"
  --output "${manifest_after}"
)
for asset_name in "${assets[@]}"; do
  resolver_args+=(--asset "${asset_name}")
done
python3 "${resolver}" "${resolver_args[@]}"

if ! cmp -s "${manifest_before}" "${manifest_after}"; then
  echo "Release or asset identity changed during exact downloads." >&2
  exit 1
fi

if ! final_repository_identity="$(repository_identity)"; then
  echo "Unable to rebind release repository identity after downloads." >&2
  exit 1
fi
if [[ "${final_repository_identity}" != "${initial_repository_identity}" ]]; then
  echo "Release repository identity changed during exact downloads." >&2
  exit 1
fi

cp "${manifest_before}" "${output_dir}/release-download-manifest.json"
trap - EXIT
rm -rf "${temp_root}"
\t' read -r asset_id asset_name expected_digest expected_size; do
  [[ -n "${asset_id}" && -n "${asset_name}" && -n "${expected_digest}" && -n "${expected_size}" ]] || {
    echo "Release download plan contains an empty field." >&2
    exit 1
  }

  partial="${output_dir}/.${asset_name}.partial"
  destination="${output_dir}/${asset_name}"
  if ! gh api \
    -H 'Accept: application/octet-stream' \
    -H 'X-GitHub-Api-Version: 2026-03-10' \
    --method GET \
    "repos/${repository}/releases/assets/${asset_id}" >"${partial}"; then
    echo "Failed to download exact release asset id ${asset_id} (${asset_name})." >&2
    exit 1
  fi

  actual_digest="$(
    python3 - "${partial}" <<'PY'
from pathlib import Path
import hashlib
import sys

path = Path(sys.argv[1])
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(f"sha256:{digest}")
PY
  )"
  if [[ "${actual_digest}" != "${expected_digest}" ]]; then
    echo "Downloaded release asset digest mismatch for ${asset_name}." >&2
    exit 1
  fi
  mv "${partial}" "${destination}"
done <"${plan}"

metadata_after="${temp_root}/release-after.json"
manifest_after="${temp_root}/manifest-after.json"
if ! gh api "${api_headers[@]}" --method GET \
  "repos/${repository}/releases/${release_id}" >"${metadata_after}"; then
  echo "Failed to re-resolve release id ${release_id} after downloads." >&2
  exit 1
fi

resolver_args=(
  --metadata "${metadata_after}"
  --repository "${repository}"
  --tag "${tag}"
  --output "${manifest_after}"
)
for asset_name in "${assets[@]}"; do
  resolver_args+=(--asset "${asset_name}")
done
python3 "${resolver}" "${resolver_args[@]}"

if ! cmp -s "${manifest_before}" "${manifest_after}"; then
  echo "Release or asset identity changed during exact downloads." >&2
  exit 1
fi

cp "${manifest_before}" "${output_dir}/release-download-manifest.json"
trap - EXIT
rm -rf "${temp_root}"
