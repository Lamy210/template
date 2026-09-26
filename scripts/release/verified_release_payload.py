from __future__ import annotations

from pathlib import Path


def validate_verified_release_payload(root: Path, dmg_name: str) -> list[str]:
    errors: list[str] = []

    if not root.exists() or not root.is_dir() or root.is_symlink():
        return ["verified release payload root must be a real directory"]

    if not isinstance(dmg_name, str) or not dmg_name or Path(dmg_name).name != dmg_name:
        return ["verified release DMG name must be a literal basename"]

    expected_names = {
        dmg_name,
        f"{dmg_name}.sha256",
        "release-provenance.json",
    }

    entries = list(root.iterdir())
    actual_names = {entry.name for entry in entries}
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        if missing:
            errors.append(f"verified release payload missing entries: {missing!r}")
        if unexpected:
            errors.append(f"verified release payload has unexpected entries: {unexpected!r}")

    for name in sorted(expected_names):
        path = root / name
        if path.is_symlink() or not path.is_file():
            errors.append(
                f"verified release payload entry must be a regular non-symlink file: {name}"
            )

    return errors
