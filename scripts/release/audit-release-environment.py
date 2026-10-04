#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.bounded_json import (  # noqa: E402
    BoundedJsonError,
    load_bounded_json_file,
)
from scripts.release.release_environment import (  # noqa: E402
    validate_release_environment,
)


def _load_json(path: Path) -> object:
    return load_bounded_json_file(path, label="release Environment audit input")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit the protected release Environment deployment-ref policy."
    )
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--policies", required=True, type=Path)
    parser.add_argument("--default-branch", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        environment = _load_json(args.environment)
        policies = _load_json(args.policies)
    except BoundedJsonError as error:
        print(f"unable to read release Environment audit input: {error}", file=sys.stderr)
        return 2

    errors = validate_release_environment(
        environment,
        policies,
        args.default_branch,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        "release Environment matches the default-branch-only deployment policy contract"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
