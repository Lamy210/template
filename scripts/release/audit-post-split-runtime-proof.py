#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.post_split_proof_evidence import (
    EvidenceError,
    build_evidence,
    write_evidence,
)
from scripts.release.post_split_runtime_proof import validate_post_split_runtime_proof
from scripts.release.unprivileged_release_build_workflow import (
    WorkflowValidationError,
    decode_github_contents_document,
    validate_unprivileged_release_build_workflow,
)


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


def _flatten_jobs(payload: object) -> object:
    if isinstance(payload, dict):
        jobs = payload.get("jobs")
        return jobs if isinstance(jobs, list) else payload

    if isinstance(payload, list) and all(isinstance(page, dict) for page in payload):
        flattened: list[object] = []
        declared_total: int | None = None
        for page in payload:
            total_count = page.get("total_count")
            if type(total_count) is int and total_count >= 0:
                if declared_total is None:
                    declared_total = total_count
                elif declared_total != total_count:
                    return {"error": "publisher job pages disagree on total_count"}
            jobs = page.get("jobs")
            if not isinstance(jobs, list):
                return {"error": "publisher job page missing jobs array"}
            flattened.extend(jobs)
        if declared_total is not None and declared_total != len(flattened):
            return {
                "error": (
                    f"publisher job total_count={declared_total} does not match "
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
    parser.add_argument("--final-repository", required=True, type=Path)
    parser.add_argument("--default-commit", required=True, type=Path)
    parser.add_argument("--final-default-commit", required=True, type=Path)
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--source-workflow", required=True, type=Path)
    parser.add_argument("--publisher-run", required=True, type=Path)
    parser.add_argument("--publisher-jobs", required=True, type=Path)
    parser.add_argument("--source-artifacts", required=True, type=Path)
    parser.add_argument("--tag-ref", required=True, type=Path)
    parser.add_argument("--tag-objects", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--archive-digest", required=True)
    parser.add_argument("--compare", required=True, type=Path)
    parser.add_argument("--evidence-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repository = _load_json(args.repository)
        final_repository = _load_json(args.final_repository)
        default_commit = _load_json(args.default_commit)
        final_default_commit = _load_json(args.final_default_commit)
        source_run = _load_json(args.source_run)
        source_workflow = _load_json(args.source_workflow)
        publisher_run = _load_json(args.publisher_run)
        publisher_jobs = _flatten_jobs(_load_json(args.publisher_jobs))
        source_artifacts = _flatten_artifacts(_load_json(args.source_artifacts))
        tag_ref = _load_json(args.tag_ref)
        tag_objects = _load_json(args.tag_objects)
        artifacts = _flatten_artifacts(_load_json(args.artifacts))
        metadata = _load_json(args.metadata)
        comparison = _load_json(args.compare)
    except (OSError, json.JSONDecodeError) as error:
        print(f"unable to read runtime proof evidence: {error}", file=sys.stderr)
        return 2

    try:
        source_workflow_text = decode_github_contents_document(source_workflow)
    except WorkflowValidationError as error:
        print(f"historical Release Build workflow evidence is invalid: {error}", file=sys.stderr)
        return 1

    source_workflow_errors = validate_unprivileged_release_build_workflow(
        source_workflow_text
    )
    for error in source_workflow_errors:
        print(f"historical Release Build workflow: {error}", file=sys.stderr)
    if source_workflow_errors:
        return 1

    if isinstance(publisher_jobs, dict) and "error" in publisher_jobs:
        print(publisher_jobs["error"], file=sys.stderr)
        return 2
    if isinstance(source_artifacts, dict) and "error" in source_artifacts:
        print(source_artifacts["error"], file=sys.stderr)
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
        source_artifacts=source_artifacts,
        tag_ref=tag_ref,
        tag_objects=tag_objects,
        publisher_jobs=publisher_jobs,
        final_repository=final_repository,
        final_default_commit=final_default_commit,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    if args.evidence_output is not None:
        try:
            evidence = build_evidence(
                repository=repository,
                default_commit=default_commit,
                final_default_commit=final_default_commit,
                source_run=source_run,
                publisher_run=publisher_run,
                publisher_jobs=publisher_jobs,
                tag_ref=tag_ref,
                tag_objects=tag_objects,
                source_artifacts=source_artifacts,
                artifacts=artifacts,
                metadata=metadata,
                archive_digest=args.archive_digest,
                comparison=comparison,
            )
            write_evidence(args.evidence_output, evidence)
        except EvidenceError as error:
            print(f"unable to write runtime proof evidence: {error}", file=sys.stderr)
            return 2
        print(f"post-split runtime proof evidence written: {args.evidence_output}")

    print(
        "post-split runtime proof is valid: historical source bytes were "
        "validated by current default-branch publisher control code"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
