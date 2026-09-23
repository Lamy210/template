#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.release_state import validate_release_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate immutable stable GitHub Release state and exact asset membership."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--asset", action="append", required=True, dest="assets")
    args = parser.parse_args()

    try:
        document = json.loads(args.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"failed to read release metadata {args.metadata}: {error}", file=sys.stderr)
        return 1

    errors = validate_release_state(
        document,
        expected_tag=args.tag,
        expected_asset_names=args.assets,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
