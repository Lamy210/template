from __future__ import annotations

import json
from pathlib import Path
import re

from scripts.release.release_attestation import (
    REPOSITORY_RE,
    SHA_RE,
    sha256_file,
    validate_release_attestation,
)
from scripts.release.release_checksum import parse_release_checksum


TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


def verify_published_release_assets(
    *,
    dmg_path: Path,
    checksum_path: Path,
    provenance_path: Path,
    expected_tag: str,
    expected_repository: str,
    expected_publisher_sha: str,
) -> tuple[list[str], str | None, str | None]:
    errors: list[str] = []

    if not isinstance(expected_tag, str) or TAG_RE.fullmatch(expected_tag) is None:
        errors.append("expected tag must match stable SemVer form vX.Y.Z")

    repository_valid = (
        isinstance(expected_repository, str)
        and REPOSITORY_RE.fullmatch(expected_repository) is not None
        and all(
            component not in {".", ".."}
            for component in expected_repository.split("/", 1)
        )
    )
    if not repository_valid:
        errors.append("expected repository must be in owner/repo form")

    if (
        not isinstance(expected_publisher_sha, str)
        or SHA_RE.fullmatch(expected_publisher_sha) is None
    ):
        errors.append("expected publisher SHA must be 40 lowercase hexadecimal characters")

    for label, path in (
        ("DMG", dmg_path),
        ("checksum", checksum_path),
        ("release provenance", provenance_path),
    ):
        if path.is_symlink() or not path.is_file():
            errors.append(f"published {label} must be a regular non-symlink file: {path}")

    if errors:
        return errors, None, None

    try:
        checksum_payload = checksum_path.read_text(encoding="utf-8")
        checksum_digest = parse_release_checksum(
            checksum_payload,
            expected_filename=dmg_path.name,
        )
    except (OSError, UnicodeError, ValueError) as error:
        errors.append(f"invalid published release checksum: {error}")
        checksum_digest = None

    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(f"invalid published release provenance: {error}")
        provenance = None

    actual_digest = sha256_file(dmg_path)
    actual_hex = actual_digest.removeprefix("sha256:")

    if checksum_digest is not None and checksum_digest != actual_hex:
        errors.append("published checksum does not match the downloaded DMG")

    provenance_errors = validate_release_attestation(provenance)
    errors.extend(f"published release provenance: {error}" for error in provenance_errors)

    source_sha: str | None = None
    if isinstance(provenance, dict):
        if provenance.get("tag") != expected_tag:
            errors.append("published release provenance tag does not match expected release tag")
        if provenance.get("sourceRepository") != expected_repository:
            errors.append(
                "published release provenance repository does not match trusted repository"
            )
        if provenance.get("publisherSHA") != expected_publisher_sha:
            errors.append(
                "published release provenance publisher SHA does not match trusted publisher"
            )
        if provenance.get("dmgSha256") != actual_digest:
            errors.append("published release provenance DMG digest does not match downloaded DMG")

        candidate_source_sha = provenance.get("sourceSHA")
        if isinstance(candidate_source_sha, str) and SHA_RE.fullmatch(candidate_source_sha):
            source_sha = candidate_source_sha

    if source_sha is None and not errors:
        errors.append("published release provenance source SHA is unavailable after validation")

    if errors:
        return errors, None, None
    return errors, actual_hex, source_sha
