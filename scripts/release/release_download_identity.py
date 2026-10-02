from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from scripts.common.repository_name import is_canonical_repository_name


TAG_RE = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_RELEASE_DMG_BYTES = 4 * 1024 * 1024 * 1024
MAX_RELEASE_METADATA_BYTES = 1024 * 1024


def _release_asset_size_limit(name: str) -> int | None:
    if name.endswith(".dmg"):
        return MAX_RELEASE_DMG_BYTES
    if name.endswith(".dmg.sha256") or name == "release-provenance.json":
        return MAX_RELEASE_METADATA_BYTES
    return None


def _validate_expected_release_asset_contract(
    names: list[str],
) -> list[str]:
    errors: list[str] = []
    dmg_names = [name for name in names if isinstance(name, str) and name.endswith(".dmg")]
    if len(names) != 3:
        errors.append("expected release asset set must contain exactly three assets")
    if len(dmg_names) != 1:
        errors.append("expected release asset set must contain exactly one DMG")
        return errors

    dmg_name = dmg_names[0]
    required = {
        dmg_name,
        f"{dmg_name}.sha256",
        "release-provenance.json",
    }
    if set(names) != required:
        errors.append(
            "expected release assets must be the DMG, its matching .sha256, "
            "and release-provenance.json"
        )
    return errors


@dataclass(frozen=True)
class ReleaseAssetIdentity:
    asset_id: int
    name: str
    digest: str
    size: int


@dataclass(frozen=True)
class ReleaseDownloadIdentity:
    repository_id: int
    repository_full_name: str
    release_id: int
    tag: str
    immutable: bool
    assets: tuple[ReleaseAssetIdentity, ...]


def _api_url_matches(
    value: object,
    *,
    repository: str,
    suffix: str,
) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return False
    parts = [part for part in parsed.path.split("/") if part]
    expected_owner, expected_name = repository.split("/", 1)
    suffix_parts = [part for part in suffix.split("/") if part]
    if len(parts) != 3 + len(suffix_parts):
        return False
    if parts[:1] != ["repos"]:
        return False
    if parts[1].casefold() != expected_owner.casefold():
        return False
    if parts[2].casefold() != expected_name.casefold():
        return False
    return parts[3:] == suffix_parts


def _browser_url_matches(
    value: object,
    *,
    repository: str,
    tag: str,
    asset_name: str,
) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return False
    parts = [part for part in parsed.path.split("/") if part]
    expected_owner, expected_name = repository.split("/", 1)
    if len(parts) != 6:
        return False
    if parts[0].casefold() != expected_owner.casefold():
        return False
    if parts[1].casefold() != expected_name.casefold():
        return False
    return parts[2:] == ["releases", "download", tag, asset_name]


def validate_release_download_identity(
    document: object,
    *,
    expected_repository: str,
    expected_repository_id: int,
    expected_tag: str,
    expected_asset_names: list[str],
) -> tuple[list[str], ReleaseDownloadIdentity | None]:
    errors: list[str] = []

    if not is_canonical_repository_name(expected_repository):
        errors.append("expected repository must use canonical owner/repo form")
    if type(expected_repository_id) is not int or expected_repository_id <= 0:
        errors.append("expected repository id must be a positive integer")
    if not isinstance(expected_tag, str) or TAG_RE.fullmatch(expected_tag) is None:
        errors.append("expected tag must match stable SemVer form vX.Y.Z")
    if not expected_asset_names:
        errors.append("expected asset set must not be empty")
    elif len(set(expected_asset_names)) != len(expected_asset_names):
        errors.append("expected asset names must be unique")
    for name in expected_asset_names:
        if not isinstance(name, str) or ASSET_NAME_RE.fullmatch(name) is None:
            errors.append(f"expected asset name is unsafe or malformed: {name!r}")
    errors.extend(_validate_expected_release_asset_contract(expected_asset_names))
    expected_set = set(expected_asset_names)

    if not isinstance(document, dict):
        errors.append("release response must be a JSON object")
        return errors, None

    release_id = document.get("id")
    if type(release_id) is not int or release_id <= 0:
        errors.append("release id must be a positive integer")

    tag_name = document.get("tag_name")
    if tag_name != expected_tag:
        errors.append(
            f"release tag identity mismatch: expected {expected_tag!r}, got {tag_name!r}"
        )

    if document.get("draft") is not False:
        errors.append("release must be published, not draft")
    if document.get("prerelease") is not False:
        errors.append("release must be stable, not prerelease")

    immutable = document.get("immutable")
    if immutable is not True:
        if type(immutable) is not bool:
            errors.append("release immutable flag must be boolean true")
        else:
            errors.append("release must be natively immutable")

    if (
        type(release_id) is int
        and release_id > 0
        and is_canonical_repository_name(expected_repository)
        and not _api_url_matches(
            document.get("url"),
            repository=expected_repository,
            suffix=f"releases/{release_id}",
        )
    ):
        errors.append("release API URL does not match repository/release identity")

    assets = document.get("assets")
    if not isinstance(assets, list):
        errors.append("release assets must be an array")
        return errors, None

    by_name: dict[str, ReleaseAssetIdentity] = {}
    seen_ids: set[int] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            errors.append("release assets must contain only JSON objects")
            continue

        asset_id = asset.get("id")
        name = asset.get("name")
        digest = asset.get("digest")
        size = asset.get("size")
        state = asset.get("state")

        if type(asset_id) is not int or asset_id <= 0:
            errors.append("release asset id must be a positive integer")
            continue
        if asset_id in seen_ids:
            errors.append(f"release asset id is duplicated: {asset_id}")
            continue
        seen_ids.add(asset_id)

        if not isinstance(name, str) or ASSET_NAME_RE.fullmatch(name) is None:
            errors.append(f"release asset name is unsafe or malformed: {name!r}")
            continue
        if name in by_name:
            errors.append(f"release asset name is duplicated: {name!r}")
            continue
        if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
            errors.append(f"release asset {name!r} has invalid SHA-256 digest")
            continue
        if type(size) is not int or size <= 0:
            errors.append(f"release asset {name!r} must have positive size")
            continue
        if name in expected_set:
            size_limit = _release_asset_size_limit(name)
            if size_limit is None:
                errors.append(f"release asset {name!r} has unsupported asset role")
                continue
            if size > size_limit:
                errors.append(
                    f"release asset {name!r} exceeds size limit: "
                    f"{size} > {size_limit}"
                )
                continue
        if state != "uploaded":
            errors.append(f"release asset {name!r} must be in uploaded state")
            continue

        if is_canonical_repository_name(expected_repository) and not _api_url_matches(
            asset.get("url"),
            repository=expected_repository,
            suffix=f"releases/assets/{asset_id}",
        ):
            errors.append(
                f"release asset {name!r} API URL does not match repository/asset identity"
            )
            continue
        if (
            is_canonical_repository_name(expected_repository)
            and isinstance(expected_tag, str)
            and TAG_RE.fullmatch(expected_tag) is not None
            and not _browser_url_matches(
                asset.get("browser_download_url"),
                repository=expected_repository,
                tag=expected_tag,
                asset_name=name,
            )
        ):
            errors.append(
                f"release asset {name!r} browser URL does not match release identity"
            )
            continue

        by_name[name] = ReleaseAssetIdentity(
            asset_id=asset_id,
            name=name,
            digest=digest,
            size=size,
        )

    actual_set = set(by_name)
    if actual_set != expected_set:
        missing = sorted(expected_set - actual_set)
        unexpected = sorted(actual_set - expected_set)
        details: list[str] = []
        if missing:
            details.append(f"missing={missing!r}")
        if unexpected:
            details.append(f"unexpected={unexpected!r}")
        errors.append(
            "release asset set does not exactly match expected immutable assets"
            + (f": {', '.join(details)}" if details else "")
        )

    if errors:
        return errors, None

    assert isinstance(release_id, int)
    assert isinstance(tag_name, str)
    assert isinstance(immutable, bool)
    ordered_assets = tuple(by_name[name] for name in expected_asset_names)
    return (
        [],
        ReleaseDownloadIdentity(
            repository_id=expected_repository_id,
            repository_full_name=expected_repository,
            release_id=release_id,
            tag=tag_name,
            immutable=immutable,
            assets=ordered_assets,
        ),
    )


def release_download_manifest(identity: ReleaseDownloadIdentity) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "repository": {
            "id": identity.repository_id,
            "fullName": identity.repository_full_name,
        },
        "releaseId": identity.release_id,
        "tag": identity.tag,
        "immutable": identity.immutable,
        "assets": [
            {
                "id": asset.asset_id,
                "name": asset.name,
                "digest": asset.digest,
                "size": asset.size,
            }
            for asset in identity.assets
        ],
    }
