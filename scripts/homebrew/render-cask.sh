#!/usr/bin/env bash
set -euo pipefail

: "${CASK_TOKEN:?CASK_TOKEN is required}"
: "${VERSION:?VERSION is required}"
: "${SHA256:?SHA256 is required}"
: "${GITHUB_OWNER:?GITHUB_OWNER is required}"
: "${GITHUB_REPO:?GITHUB_REPO is required}"
: "${DMG_BASENAME:?DMG_BASENAME is required}"
: "${APP_NAME:?APP_NAME is required}"
: "${DESCRIPTION:?DESCRIPTION is required}"
: "${HOMEPAGE:?HOMEPAGE is required}"
: "${BUNDLE_ID:?BUNDLE_ID is required}"
: "${OUTPUT_CASK:?OUTPUT_CASK is required}"
: "${CASK_OUTPUT_ROOT:?CASK_OUTPUT_ROOT is required}"

TEMPLATE_PATH="${CASK_TEMPLATE:-templates/homebrew/Cask.rb.template}"

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  echo "Cask template not found: ${TEMPLATE_PATH}" >&2
  exit 1
fi

validate_output_path() {
  python3 "$(dirname "${BASH_SOURCE[0]}")/validate-cask-output-path.py" \
    --root "${CASK_OUTPUT_ROOT}" \
    --output "${OUTPUT_CASK}"
}

validate_output_path
mkdir -p "$(dirname "${OUTPUT_CASK}")"
validate_output_path

python3 - "${TEMPLATE_PATH}" "${OUTPUT_CASK}" <<'PY'
import os
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
text = source.read_text(encoding="utf-8")

keys = (
    "CASK_TOKEN",
    "VERSION",
    "SHA256",
    "GITHUB_OWNER",
    "GITHUB_REPO",
    "DMG_BASENAME",
    "APP_NAME",
    "DESCRIPTION",
    "HOMEPAGE",
    "BUNDLE_ID",
)


def ruby_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("#{", "\\#{")
    )


dmg_basename = os.environ["DMG_BASENAME"]
if re.fullmatch(
    r"[A-Za-z0-9._+-]*#\{version\}[A-Za-z0-9._+-]*\.dmg",
    dmg_basename,
) is None:
    raise SystemExit(
        "DMG_BASENAME must be a literal DMG basename with exactly one #{version} placeholder"
    )

for key in keys:
    value = os.environ[key]
    if key == "DMG_BASENAME":
        rendered = ruby_string(value).replace(r"\#{version}", "#{version}")
    else:
        rendered = ruby_string(value)
    text = text.replace("{{" + key + "}}", rendered)

if "{{" in text or "}}" in text:
    raise SystemExit("Unresolved placeholder remains in rendered Cask")

target.write_text(text, encoding="utf-8")
PY

printf 'Rendered %s\n' "${OUTPUT_CASK}"
