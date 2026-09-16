#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: export-coverage.sh --adapter <xcode|swiftpm> --input <path> --output <json> --profile <json>

Normalize Xcode xccov or SwiftPM exported JSON into the repository coverage schema.
For SwiftPM, --input is the JSON path printed by `swift test --show-codecov-path`.
For Xcode, --input is an .xcresult bundle read via `xcrun xccov view --report --json`.
EOF
}

adapter=""
input=""
output=""
profile=""

while (($#)); do
  case "$1" in
    --adapter)
      adapter="${2:-}"
      shift 2
      ;;
    --input)
      input="${2:-}"
      shift 2
      ;;
    --output)
      output="${2:-}"
      shift 2
      ;;
    --profile)
      profile="${2:-}"
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

if [[ "$adapter" != "xcode" && "$adapter" != "swiftpm" ]]; then
  echo "error: --adapter must be xcode or swiftpm" >&2
  exit 2
fi
if [[ -z "$input" || -z "$output" || -z "$profile" ]]; then
  echo "error: --input, --output, and --profile are required" >&2
  exit 2
fi
if [[ ! -e "$input" ]]; then
  echo "error: coverage input does not exist: $input" >&2
  exit 2
fi
if [[ ! -f "$profile" ]]; then
  echo "error: coverage profile does not exist: $profile" >&2
  exit 2
fi

raw="$input"
tmp=""
cleanup() {
  if [[ -n "$tmp" ]]; then
    rm -f "$tmp"
  fi
}
trap cleanup EXIT

if [[ "$adapter" == "xcode" ]]; then
  tmp="$(mktemp)"
  xcrun xccov view --report --json "$input" >"$tmp"
  raw="$tmp"
fi

mkdir -p "$(dirname "$output")"
python3 - "$adapter" "$raw" "$profile" "$output" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

adapter, raw_path, profile_path, output_path = sys.argv[1:]


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def load(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read JSON {path}: {exc}")


def counts(covered: Any, executable: Any, field: str) -> dict[str, Any]:
    if isinstance(covered, bool) or not isinstance(covered, int):
        fail(f"{field}.coveredLines must be an integer")
    if isinstance(executable, bool) or not isinstance(executable, int):
        fail(f"{field}.executableLines must be an integer")
    if covered < 0 or executable < 0 or covered > executable:
        fail(f"{field} contains impossible covered/executable line counts")
    ratio = 0.0 if executable == 0 else covered / executable
    return {
        "coveredLines": covered,
        "executableLines": executable,
        "lineCoverage": ratio,
    }


raw = load(raw_path)
profile = load(profile_path)
if not isinstance(profile, dict):
    fail("coverage profile must be a JSON object")

profile_payload = {
    "schemaVersion": 1,
    "adapter": adapter,
    "profile": profile,
}
canonical_profile = json.dumps(
    profile_payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
fingerprint = "sha256:" + hashlib.sha256(canonical_profile).hexdigest()

targets: dict[str, Any] = {}
if adapter == "swiftpm":
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list) or len(raw["data"]) != 1:
        fail("SwiftPM coverage JSON must contain exactly one data entry")
    entry = raw["data"][0]
    try:
        lines = entry["totals"]["lines"]
        totals = counts(lines["covered"], lines["count"], "totals")
    except (KeyError, TypeError):
        fail("SwiftPM coverage JSON is missing totals.lines.count/covered")
elif adapter == "xcode":
    if not isinstance(raw, dict):
        fail("Xcode coverage JSON must be an object")
    try:
        totals = counts(raw["coveredLines"], raw["executableLines"], "totals")
    except KeyError:
        fail("Xcode coverage JSON is missing coveredLines/executableLines")

    raw_targets = raw.get("targets", [])
    if not isinstance(raw_targets, list):
        fail("Xcode coverage targets must be an array")
    candidate_targets: dict[str, Any] = {}
    reliable = True
    for index, target in enumerate(raw_targets):
        if not isinstance(target, dict):
            fail(f"targets[{index}] must be an object")
        name = target.get("name")
        if not isinstance(name, str) or not name:
            reliable = False
            continue
        if name in candidate_targets:
            reliable = False
            continue
        try:
            candidate_targets[name] = counts(
                target["coveredLines"], target["executableLines"], f"targets[{name}]"
            )
        except KeyError:
            reliable = False
    if reliable:
        targets = candidate_targets
else:
    fail(f"unsupported adapter: {adapter}")

result = {
    "schemaVersion": 1,
    "coverageProfileFingerprint": fingerprint,
    "totals": totals,
    "targets": targets,
}
Path(output_path).write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
