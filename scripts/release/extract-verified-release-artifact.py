#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.verified_release_archive import (  # noqa: E402
    validate_and_extract_verified_release_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an exact signer-produced Actions Artifact ZIP by its "
            "GitHub-provided digest and extract the exact release payload."
        )
    )
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dmg-name", required=True)
    parser.add_argument("--expected-digest", required=True)
    args = parser.parse_args()

    errors = validate_and_extract_verified_release_artifact(
        args.archive,
        args.output,
        dmg_name=args.dmg_name,
        expected_digest=args.expected_digest,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
