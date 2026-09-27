#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.unprivileged_release_build_workflow import (
    load_and_validate_github_contents,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed unless a historical Release Build workflow is compatible "
            "with the unprivileged post-split runtime-proof boundary."
        )
    )
    parser.add_argument("--github-content-json", required=True, type=Path)
    args = parser.parse_args()

    errors = load_and_validate_github_contents(args.github_content_json)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print("historical Release Build workflow is unprivileged and proof-compatible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
