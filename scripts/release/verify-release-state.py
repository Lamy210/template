#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.release_asset_limits import (
    MAX_RELEASE_METADATA_JSON_BYTES,
)
from scripts.release.release_state import validate_release_state
from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    snapshot_regular_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate immutable stable GitHub Release state and exact asset membership."
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--asset", action="append", required=True, dest="assets")
    args = parser.parse_args()

    try:
        with snapshot_regular_file(
            args.metadata,
            prefix="release-state-metadata.",
            max_bytes=MAX_RELEASE_METADATA_JSON_BYTES,
        ) as metadata_snapshot:
            document = json.loads(
                metadata_snapshot.read_text(encoding="utf-8")
            )
    except (
        RegularFileSnapshotError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"failed to read bounded release metadata {args.metadata}: {error}",
            file=sys.stderr,
        )
        return 1

    errors = validate_release_state(
        document,
        expected_tag=args.tag,
        expected_asset_names=args.assets,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
