#!/usr/bin/env python3
from __future__ import annotations

import argparse

from artifact_identity import normalize_uploaded_artifact_identity


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize upload-artifact identity for an exact cross-job handoff."
    )
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-digest", required=True)
    args = parser.parse_args()

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
