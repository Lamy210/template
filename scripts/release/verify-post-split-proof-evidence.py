#!/usr/bin/env python3
"""Validate a preserved post-split runtime proof evidence document offline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.bounded_json import (  # noqa: E402
    BoundedJsonError,
    load_bounded_json_file,
)
from scripts.release.post_split_proof_evidence import (  # noqa: E402
    validate_evidence_document,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()

    try:
        document = load_bounded_json_file(
            args.evidence,
            label="post-split proof evidence",
        )
    except BoundedJsonError as error:
        print(f"unable to read proof evidence: {error}", file=sys.stderr)
        return 2

    errors = validate_evidence_document(document)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        "post-split proof evidence is structurally valid and internally consistent"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
