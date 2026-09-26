#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.post_split_runtime_proof import validate_post_split_runtime_proof


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _flatten_artifacts(payload: object) -> object:
    if isinstance(payload, dict):
        artifacts = payload.get("artifacts")
        return artifacts if isinstance(artifacts, list) else payload

    if isinstance(payload, list) and all(isinstance(page, dict) for page in payload):
        flattened: list[object] = []
        declared_total: int | None = None
        for page in payload:
            total_count = page.get("total_count")
            if type(total_count) is int and total_count >= 0:
                if declared_total is None:
                    declared_total = total_count
                elif declared_total != total_count:
                    return {"error": "artifact pages disagree on total_count"}
            artifacts = page.get("artifacts")
            if not isinstance(artifacts, list):
                return {"error": "artifact page missing artifacts array"}
            flattened.extend(artifacts)
        if declared_total is not None and declared_total != len(flattened):
            return {
                "error": (
                    f"artifact total_count={declared_total} does not match "
                    f"fetched entries={len(flattened)}"
                )
            }
        return flattened

    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a disposable-repository post-split ancestor runtime proof "
            "for the two-stage macOS release architecture."
        )
    )
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--default-commit", required=True, type=Path)
    parser.add_argument("--final-default-commit", required=True, type=Path)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--publisher-run", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--archive-digest", required=True)
    parser.add_argument("--compare", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repository = _load_json(args.repository)
        default_commit = _load_json(args.default_commit)
        final_default_commit = _load_json(args.final_default_commit)
        source_run = _load_json(args.source_run)
        publisher_run = _load_json(args.publisher_run)
        artifacts = _flatten_artifacts(_load_json(args.artifacts))
        metadata = _load_json(args.metadata)
        comparison = _load_json(args.compare)
    except (OSError, json.JSONDecodeError) as error:
        print(f"unable to read runtime proof evidence: {error}", file=sys.stderr)
        return 2

    if isinstance(artifacts, dict) and "error" in artifacts:
        print(artifacts["error"], file=sys.stderr)
        return 2

    errors = validate_post_split_runtime_proof(
        repository,
        default_commit,
        source_run,
        publisher_run,
        artifacts,
        metadata,
        args.archive_digest,
        comparison,
        final_default_commit=final_default_commit,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        "post-split runtime proof is valid: historical source bytes were "
        "validated by current default-branch publisher control code"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
