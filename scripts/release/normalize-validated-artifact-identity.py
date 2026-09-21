#!/usr/bin/env python3
from __future__ import annotations

import argparse

from artifact_identity import normalize_uploaded_artifact_identity


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize upload-artifact identity before crossing a privileged boundary."
    )
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-digest", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        artifact_id, digest = normalize_uploaded_artifact_identity(
            args.artifact_id,
            args.artifact_digest,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    print(f"id={artifact_id}")
    print(f"digest={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
