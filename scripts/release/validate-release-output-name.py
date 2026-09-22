#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.release_output_name import validate_dmg_name


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate privileged release output filenames before secrets are used."
    )
    parser.add_argument("--dmg-name", required=True)
    args = parser.parse_args()

    errors = validate_dmg_name(args.dmg_name)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
