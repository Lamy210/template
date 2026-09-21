#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from release_environment import validate_release_environment


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
    except (OSError, json.JSONDecodeError) as error:
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
