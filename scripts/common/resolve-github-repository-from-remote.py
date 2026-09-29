#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.github_remote import repository_from_github_remote  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a canonical owner/repo identity from a GitHub remote URL."
    )
    parser.add_argument("remote")
    args = parser.parse_args()

    try:
        repository = repository_from_github_remote(args.remote)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    print(repository)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
