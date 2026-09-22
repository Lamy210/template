#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys


DMG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.dmg$")


def validate_dmg_name(value: object) -> list[str]:
    if not isinstance(value, str) or DMG_NAME_RE.fullmatch(value) is None:
        return ["DMG name must be a safe literal .dmg basename"]
    return []


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
