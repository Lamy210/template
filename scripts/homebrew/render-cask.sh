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

TEMPLATE_PATH="${CASK_TEMPLATE:-templates/homebrew/Cask.rb.template}"

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  echo "Cask template not found: ${TEMPLATE_PATH}" >&2
  exit 1
fi

mkdir -p "$(dirname "${OUTPUT_CASK}")"

python3 - "${TEMPLATE_PATH}" "${OUTPUT_CASK}" <<'PY'
import os
import pathlib
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

for key in keys:
    text = text.replace("{{" + key + "}}", os.environ[key])

if "{{" in text or "}}" in text:
    raise SystemExit("Unresolved placeholder remains in rendered Cask")

target.write_text(text, encoding="utf-8")
PY

printf 'Rendered %s\n' "${OUTPUT_CASK}"
