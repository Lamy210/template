#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.homebrew.cask_asset import validate_cask_asset_mapping  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bind a Homebrew Cask DMG template to the exact published release asset."
    )
    parser.add_argument("--source-tag", required=True)
    parser.add_argument("--dmg-name", required=True)
    parser.add_argument("--dmg-basename-template", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_cask_asset_mapping(
        source_tag=args.source_tag,
        dmg_name=args.dmg_name,
        dmg_basename_template=args.dmg_basename_template,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print("Cask DMG template matches published DMG identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
