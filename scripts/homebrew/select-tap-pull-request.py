#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.homebrew.tap_pr_selection import select_same_repository_pull_request


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select an unambiguous same-repository Homebrew automation pull request."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()

    try:
        document = json.loads(args.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"failed to read tap pull request metadata {args.metadata}: {error}", file=sys.stderr)
        return 1

    errors, number = select_same_repository_pull_request(
        document,
        expected_repository=args.repository,
        expected_head=args.head,
        expected_base=args.base,
        expected_head_sha=args.head_sha,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    if number is not None:
        print(number)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
