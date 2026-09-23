#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.published_release_assets import verify_published_release_assets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify published DMG, checksum, and final provenance as one release identity."
    )
    parser.add_argument("--dmg", required=True, type=Path)
    parser.add_argument("--checksum", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    errors, digest = verify_published_release_assets(
        dmg_path=args.dmg,
        checksum_path=args.checksum,
        provenance_path=args.provenance,
        expected_tag=args.tag,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors or digest is None:
        return 1

    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
