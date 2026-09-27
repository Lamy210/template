#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.runtime_proof_source_artifact import (
    verify_runtime_proof_source_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the exact Release Build Artifact ZIP used by a post-split "
            "runtime proof and bind its unsigned app archive bytes."
        )
    )
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-artifact-digest", required=True)
    parser.add_argument("--expected-app-archive-digest", required=True)
    args = parser.parse_args()

    errors = verify_runtime_proof_source_artifact(
        args.archive,
        args.output,
        expected_artifact_digest=args.expected_artifact_digest,
        expected_app_archive_digest=args.expected_app_archive_digest,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        "source Artifact bytes are bound to the validated unsigned app archive"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
