#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


DMG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.dmg$")
CHECKSUM_LINE_RE = re.compile(
    r"^(?P<digest>[0-9a-f]{64})  (?P<filename>[A-Za-z0-9][A-Za-z0-9._+-]*\.dmg)\n$"
)


def parse_release_checksum(payload: str, *, expected_filename: str) -> str:
    if DMG_NAME_RE.fullmatch(expected_filename) is None:
        raise ValueError("expected DMG filename must be a safe literal .dmg basename")

    match = CHECKSUM_LINE_RE.fullmatch(payload)
    if match is None:
        raise ValueError(
            "checksum asset must contain exactly one canonical shasum line "
            "'<64 lowercase hex><two spaces><DMG basename>\\n'"
        )

    filename = match.group("filename")
    if filename != expected_filename:
        raise ValueError(
            f"checksum filename mismatch: expected {expected_filename!r}, got {filename!r}"
        )
    return match.group("digest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a canonical DMG checksum asset and print its SHA-256."
    )
    parser.add_argument("checksum", type=Path)
    parser.add_argument("expected_filename")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = args.checksum.read_text(encoding="utf-8")
        digest = parse_release_checksum(
            payload,
            expected_filename=args.expected_filename,
        )
    except (OSError, UnicodeError, ValueError) as error:
        print(f"invalid release checksum: {error}", file=sys.stderr)
        return 1

    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
