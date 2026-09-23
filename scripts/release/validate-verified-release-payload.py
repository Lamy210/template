#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from verified_release_payload import validate_verified_release_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the exact signer-to-publisher release payload."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--dmg-name", required=True)
    args = parser.parse_args()

    errors = validate_verified_release_payload(args.root, args.dmg_name)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
