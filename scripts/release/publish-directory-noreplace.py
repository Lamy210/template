#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.atomic_directory_publish import (  # noqa: E402
    AtomicDirectoryPublishError,
    atomic_publish_directory_noreplace,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Atomically publish one directory without replacing a destination."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    try:
        atomic_publish_directory_noreplace(args.source, args.destination)
    except AtomicDirectoryPublishError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
