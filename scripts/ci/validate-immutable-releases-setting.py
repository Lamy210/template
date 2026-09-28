#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.immutable_releases_setting import (  # noqa: E402
    validate_immutable_releases_setting,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate GitHub native immutable-releases repository settings."
        )
    )
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()

    try:
        document = json.loads(args.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"failed to read immutable releases metadata: {error}", file=sys.stderr)
        return 1

    errors, setting = validate_immutable_releases_setting(document)
    for error in errors:
        print(error, file=sys.stderr)
    if errors or setting is None:
        return 1

    print("enabled=true")
    print(
        "enforced_by_owner="
        + ("true" if setting.enforced_by_owner else "false")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
