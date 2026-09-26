#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: collect-metadata.sh --output <profile.json> --profile-id <id> --current-sha <sha> \
  --runner-family <name> --architecture <arch> --xcode-policy <policy> \
  --locale <locale> --language <language> --timezone <tz> --appearance <appearance> \
  --display-scale <scale> --capture-geometry <geometry> --fixture-version <version> \
  --capture-contract-version <n> --comparator-schema-version <n>
USAGE
}

output=""
profile_id=""
current_sha=""
runner_family=""
architecture=""
xcode_policy=""
locale=""
language=""
timezone=""
appearance=""
display_scale=""
capture_geometry=""
fixture_version=""
capture_contract_version=""
comparator_schema_version=""

while (($#)); do
  case "$1" in
    --output)
      output="${2:-}"
      shift 2
      ;;
    --profile-id)
      profile_id="${2:-}"
      shift 2
      ;;
    --current-sha)
      current_sha="${2:-}"
      shift 2
      ;;
    --runner-family)
      runner_family="${2:-}"
      shift 2
      ;;
    --architecture)
      architecture="${2:-}"
      shift 2
      ;;
    --xcode-policy)
      xcode_policy="${2:-}"
      shift 2
      ;;
    --locale)
      locale="${2:-}"
      shift 2
      ;;
    --language)
      language="${2:-}"
      shift 2
      ;;
    --timezone)
      timezone="${2:-}"
      shift 2
      ;;
    --appearance)
      appearance="${2:-}"
      shift 2
      ;;
    --display-scale)
      display_scale="${2:-}"
      shift 2
      ;;
    --capture-geometry)
      capture_geometry="${2:-}"
      shift 2
      ;;
    --fixture-version)
      fixture_version="${2:-}"
      shift 2
      ;;
    --capture-contract-version)
      capture_contract_version="${2:-}"
      shift 2
      ;;
    --comparator-schema-version)
      comparator_schema_version="${2:-}"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_non_empty() {
  local name="$1"
  local value="$2"
  if [[ -z "${value//[[:space:]]/}" ]]; then
    echo "error: ${name} must not be empty" >&2
    exit 2
  fi
}

for pair in \
  "output=${output}" \
  "profile-id=${profile_id}" \
  "current-sha=${current_sha}" \
  "runner-family=${runner_family}" \
  "architecture=${architecture}" \
  "xcode-policy=${xcode_policy}" \
  "locale=${locale}" \
  "language=${language}" \
  "timezone=${timezone}" \
  "appearance=${appearance}" \
  "display-scale=${display_scale}" \
  "capture-geometry=${capture_geometry}" \
  "fixture-version=${fixture_version}"; do
  require_non_empty "${pair%%=*}" "${pair#*=}"
done

for version in "${capture_contract_version}" "${comparator_schema_version}"; do
  [[ "${version}" =~ ^[0-9]+$ ]] || {
    echo "error: controlled schema versions must be positive integers" >&2
    exit 2
  }
  ((10#${version} > 0)) || {
    echo "error: controlled schema versions must be positive integers" >&2
    exit 2
  }
done

macos_build="$(sw_vers -buildVersion)"
runner_image_version="${ImageVersion:-unknown}"
xcode_build="$(xcodebuild -version | awk 'NR == 1 { printf "%s", $0; next } { printf " | %s", $0 } END { printf "\n" }')"

mkdir -p "$(dirname "${output}")"

python3 - \
  "${output}" "${profile_id}" "${current_sha}" "${runner_family}" "${architecture}" \
  "${xcode_policy}" "${locale}" "${language}" "${timezone}" "${appearance}" \
  "${display_scale}" "${capture_geometry}" "${fixture_version}" \
  "${capture_contract_version}" "${comparator_schema_version}" \
  "${macos_build}" "${runner_image_version}" "${xcode_build}" <<'PY'
import hashlib
import json
import sys

(
    output, profile_id, current_sha, runner_family, architecture, xcode_policy,
    locale, language, timezone, appearance, display_scale, capture_geometry,
    fixture_version, capture_contract_version, comparator_schema_version,
    macos_build, runner_image_version, xcode_build,
) = sys.argv[1:]

controlled = {
    "runnerFamily": runner_family,
    "architecture": architecture,
    "xcodePolicy": xcode_policy,
    "locale": locale,
    "language": language,
    "timezone": timezone,
    "appearance": appearance,
    "displayScale": display_scale,
    "captureGeometry": capture_geometry,
    "fixtureVersion": fixture_version,
    "captureContractVersion": int(capture_contract_version),
    "comparatorSchemaVersion": int(comparator_schema_version),
}
canonical = json.dumps(controlled, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

payload = {
    "schemaVersion": 2,
    "profile": profile_id,
    "controlled": controlled,
    "observed": {
        "macOSBuild": macos_build,
        "runnerImageVersion": runner_image_version,
        "xcodeBuild": xcode_build,
    },
    "profileFingerprint": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    "currentSHA": current_sha,
}

with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write("\n")
PY
