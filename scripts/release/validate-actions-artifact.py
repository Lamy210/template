#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from actions_artifact import validate_and_extract_release_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and extract exact release Actions Artifact ZIP.")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    errors = validate_and_extract_release_artifact(args.archive, args.output)
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
