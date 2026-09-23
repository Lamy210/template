#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.release_state import validate_release_expectations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate stable release tag and immutable asset expectations before publication."
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--asset", action="append", required=True, dest="assets")
    args = parser.parse_args()

    errors = validate_release_expectations(
        expected_tag=args.tag,
        expected_asset_names=args.assets,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
