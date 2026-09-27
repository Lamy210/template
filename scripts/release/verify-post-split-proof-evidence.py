#!/usr/bin/env python3
"""Validate a preserved post-split runtime proof evidence document offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.post_split_proof_evidence import validate_evidence_document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()

    try:
        with args.evidence.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
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
