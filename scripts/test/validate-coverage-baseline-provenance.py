#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.bounded_json import (  # noqa: E402
    BoundedJsonError,
    load_bounded_json_file,
)
from scripts.test.coverage_baseline_provenance import (  # noqa: E402
    ValidationError,
    validate_coverage_baseline_provenance,
)


def load_json(path: Path, label: str):
    try:
        return load_bounded_json_file(path, label=label)
    except BoundedJsonError as error:
        raise ValidationError(f"failed to read {label}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate trusted coverage baseline provenance against resolver metadata."
    )
    parser.add_argument("--resolver-metadata", required=True, type=Path)
    parser.add_argument("--baseline-provenance", required=True, type=Path)
    parser.add_argument("--baseline-summary", required=True, type=Path)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-workflow", required=True)
    parser.add_argument("--expected-artifact", required=True)
    args = parser.parse_args()

    try:
        result = validate_coverage_baseline_provenance(
            load_json(args.resolver_metadata, "resolver metadata"),
            load_json(args.baseline_provenance, "coverage baseline provenance"),
            load_json(args.baseline_summary, "coverage baseline summary"),
            expected_repository=args.expected_repository,
            expected_workflow=args.expected_workflow,
            expected_artifact=args.expected_artifact,
        )
    except ValidationError as error:
        print(error, file=sys.stderr)
        return 1

    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
