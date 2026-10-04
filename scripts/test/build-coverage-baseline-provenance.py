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
    build_coverage_baseline_provenance,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build trusted coverage baseline provenance."
    )
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--artifact-name", required=True)
    args = parser.parse_args()

    try:
        summary = load_bounded_json_file(args.summary, label="coverage summary")
        payload = build_coverage_baseline_provenance(
            summary,
            repository=args.repository,
            repository_id=args.repository_id,
            workflow=args.workflow,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            source_sha=args.source_sha,
            artifact_name=args.artifact_name,
        )
    except (BoundedJsonError, ValidationError) as error:
        print(error, file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
