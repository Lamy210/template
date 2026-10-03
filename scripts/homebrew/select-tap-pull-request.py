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
from scripts.homebrew.tap_pr_selection import (  # noqa: E402
    normalize_rest_pull_request_pages,
    select_same_repository_pull_request,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select an unambiguous same-repository Homebrew automation pull request."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--head", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument(
        "--rest-pages",
        action="store_true",
        help="Interpret metadata as gh api --paginate --slurp REST pull-request pages.",
    )
    args = parser.parse_args()

    try:
        document = load_bounded_json_file(
            args.metadata,
            label="tap pull request metadata",
        )
    except BoundedJsonError as error:
        print(error, file=sys.stderr)
        return 1

    if args.rest_pages:
        normalization_errors, document = normalize_rest_pull_request_pages(
            document,
            expected_repository=args.repository,
            expected_repository_id=args.repository_id,
        )
        for error in normalization_errors:
            print(error, file=sys.stderr)
        if normalization_errors:
            return 1

    errors, number = select_same_repository_pull_request(
        document,
        expected_repository=args.repository,
        expected_repository_id=args.repository_id,
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
