#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.runtime_proof_artifact import extract_runtime_proof_metadata


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify an exact post-split proof Artifact ZIP and extract validated metadata."
    )
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--app-archive-digest-output", required=True, type=Path)
    args = parser.parse_args()

    errors = extract_runtime_proof_metadata(
        args.archive,
        args.output,
        expected_digest=args.expected_digest,
        app_archive_digest_output_path=args.app_archive_digest_output,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
