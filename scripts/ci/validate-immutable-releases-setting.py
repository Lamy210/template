#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.immutable_releases_setting import (  # noqa: E402
    validate_immutable_releases_setting,
)
from scripts.common.bounded_json import (  # noqa: E402
    BoundedJsonError,
    load_bounded_json_file,
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
        document = load_bounded_json_file(
            args.metadata,
            label="immutable releases metadata",
        )
    except BoundedJsonError as error:
        print(error, file=sys.stderr)
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
