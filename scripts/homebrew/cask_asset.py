from __future__ import annotations

import re

from scripts.release.release_output_name import validate_dmg_name


TAG_RE = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
DMG_TEMPLATE_RE = re.compile(
    r"^[A-Za-z0-9._+-]*#\{version\}[A-Za-z0-9._+-]*\.dmg$"
)


def validate_cask_asset_mapping(
    *,
    source_tag: str,
    dmg_name: str,
    dmg_basename_template: str,
) -> list[str]:
    errors: list[str] = []

    if TAG_RE.fullmatch(source_tag) is None:
        errors.append("source_tag must use stable SemVer form vX.Y.Z")

    errors.extend(validate_dmg_name(dmg_name))

    if DMG_TEMPLATE_RE.fullmatch(dmg_basename_template) is None:
        errors.append(
            "dmg_basename_template must be a safe .dmg basename with exactly one "
            "#{version} placeholder"
        )

    if errors:
        return errors

    version = source_tag[1:]
    expanded = dmg_basename_template.replace("#{version}", version)
    if expanded != dmg_name:
        errors.append(
            "dmg_basename_template must expand exactly to dmg_name for source_tag: "
            f"expected {dmg_name!r}, got {expanded!r}"
        )

    return errors
