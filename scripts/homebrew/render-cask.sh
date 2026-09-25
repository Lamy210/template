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

python3 - "${TEMPLATE_PATH}" "${OUTPUT_CASK}" <<'PY'
import os
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
text = source.read_text(encoding="utf-8")

target_parent = target.parent
if target.is_symlink():
    raise SystemExit(f"OUTPUT_CASK must not be a symbolic link: {target}")
if target_parent.is_symlink():
    raise SystemExit(f"OUTPUT_CASK parent must not be a symbolic link: {target_parent}")

target_parent.mkdir(parents=True, exist_ok=True)
if target_parent.is_symlink() or not target_parent.is_dir():
    raise SystemExit(f"OUTPUT_CASK parent must be a real directory: {target_parent}")

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

flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW

try:
    descriptor = os.open(target, flags, 0o644)
except OSError as error:
    raise SystemExit(f"Unable to open OUTPUT_CASK safely: {error}") from error

with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(text)
PY

printf 'Rendered %s\n' "${OUTPUT_CASK}"
