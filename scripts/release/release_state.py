from __future__ import annotations

from collections import Counter
from pathlib import Path
import re


TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def validate_release_state(
    document: object,
    *,
    expected_tag: str,
    expected_asset_names: list[str],
) -> list[str]:
    errors: list[str] = []

    if not isinstance(expected_tag, str) or TAG_RE.fullmatch(expected_tag) is None:
        errors.append("expected release tag must match stable SemVer form vX.Y.Z")

    if not expected_asset_names:
        errors.append("expected release asset set must not be empty")
    elif len(set(expected_asset_names)) != len(expected_asset_names):
        errors.append("expected release asset names must be unique")

    for name in expected_asset_names:
        if not isinstance(name, str) or ASSET_NAME_RE.fullmatch(name) is None:
            errors.append(f"expected release asset name is unsafe or malformed: {name!r}")

    if not isinstance(document, dict):
        errors.append("release metadata must be a JSON object")
        return errors

    tag_name = document.get("tagName")
    if not isinstance(tag_name, str) or tag_name != expected_tag:
        errors.append(
            f"release tag identity mismatch: expected {expected_tag!r}, got {tag_name!r}"
        )

    if document.get("isDraft") is not False:
        errors.append("release must be published, not draft")
    if document.get("isPrerelease") is not False:
        errors.append("release must be stable, not prerelease")

    assets = document.get("assets")
    if not isinstance(assets, list):
        errors.append("release assets metadata must be an array")
        return errors

    actual_names: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            errors.append("release asset metadata must contain only objects")
            continue
        name = asset.get("name")
        if not isinstance(name, str) or not name:
            errors.append("release asset name must be a non-empty string")
            continue
        actual_names.append(name)

    actual = Counter(actual_names)
    expected = Counter(expected_asset_names)
    if actual != expected:
        missing = sorted((expected - actual).elements())
        unexpected = sorted((actual - expected).elements())
        details = []
        if missing:
            details.append(f"missing={missing!r}")
        if unexpected:
            details.append(f"unexpected={unexpected!r}")
        errors.append(
            "release asset set does not exactly match immutable publication contract"
            + (f": {', '.join(details)}" if details else "")
        )

    return errors
