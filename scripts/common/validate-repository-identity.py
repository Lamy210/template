#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.repository_identity import validate_repository_identity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and print a stable GitHub repository identity."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    try:
        document = json.loads(args.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"failed to read repository metadata: {error}", file=sys.stderr)
        return 1

    errors, identity = validate_repository_identity(
        document,
        expected_repository=args.repository,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors or identity is None:
        return 1

    print(identity.repository_id)
    print(identity.full_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
