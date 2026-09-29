#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.repository_merge_settings import (  # noqa: E402
    validate_repository_merge_settings,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the repository merge-policy desired state."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    try:
        document = json.loads(args.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"failed to read repository metadata: {error}", file=sys.stderr)
        return 1

    errors, settings = validate_repository_merge_settings(
        document,
        expected_repository=args.repository,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors or settings is None:
        return 1

    print(f"repository_id={settings.repository_id}")
    print(f"repository={settings.full_name.casefold()}")
    print("allow_squash_merge=true")
    print("allow_merge_commit=false")
    print("allow_rebase_merge=false")
    print("delete_branch_on_merge=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
