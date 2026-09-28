#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.release_download_identity import (  # noqa: E402
    release_download_manifest,
    validate_release_download_identity,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one GitHub REST release object and persist the exact "
            "release/asset IDs and digests used for downstream downloads."
        )
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--asset", action="append", required=True, dest="assets")
    parser.add_argument(
        "--require-immutable",
        action="store_true",
        help="Require the GitHub Release object to report immutable=true.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        document = json.loads(args.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"failed to read release metadata: {error}", file=sys.stderr)
        return 1

    errors, identity = validate_release_download_identity(
        document,
        expected_repository=args.repository,
        expected_tag=args.tag,
        expected_asset_names=args.assets,
        require_immutable=args.require_immutable,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors or identity is None:
        return 1

    manifest = release_download_manifest(identity)
    try:
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
    except OSError as error:
        print(f"failed to write release download manifest: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
