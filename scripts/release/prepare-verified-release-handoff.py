#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.verified_release_handoff import (  # noqa: E402
    prepare_verified_release_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Snapshot and validate the exact signer-to-publisher release handoff."
        )
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dmg-name", required=True)
    args = parser.parse_args()

    errors = prepare_verified_release_handoff(
        args.source,
        args.output,
        dmg_name=args.dmg_name,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
