from __future__ import annotations


MAX_RELEASE_DMG_BYTES = 4 * 1024 * 1024 * 1024
MAX_RELEASE_METADATA_BYTES = 1024 * 1024
VERIFIED_RELEASE_ZIP_OVERHEAD_BYTES = 16 * 1024 * 1024
MAX_VERIFIED_RELEASE_ZIP_BYTES = (
    MAX_RELEASE_DMG_BYTES
    + 2 * MAX_RELEASE_METADATA_BYTES
    + VERIFIED_RELEASE_ZIP_OVERHEAD_BYTES
)


def release_asset_size_limit(name: str, *, dmg_name: str | None = None) -> int | None:
    if dmg_name is not None and name == dmg_name:
        return MAX_RELEASE_DMG_BYTES
    if name.endswith(".dmg"):
        return MAX_RELEASE_DMG_BYTES
    if name.endswith(".dmg.sha256") or name == "release-provenance.json":
        return MAX_RELEASE_METADATA_BYTES
    return None


__all__ = [
    "MAX_RELEASE_DMG_BYTES",
    "MAX_RELEASE_METADATA_BYTES",
    "MAX_VERIFIED_RELEASE_ZIP_BYTES",
    "VERIFIED_RELEASE_ZIP_OVERHEAD_BYTES",
    "release_asset_size_limit",
]
